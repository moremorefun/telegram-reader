#!/usr/bin/env python3
"""
Telegram MCP CLI 工具
用于登录和管理 session
"""

import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient

from .config import (
    API_ID, API_HASH, CONFIG_DIR, ENV_FILE,
    get_session_path, is_configured, has_session
)


def setup_env():
    """设置环境变量配置"""
    print("=" * 50)
    print("Telegram MCP 配置向导")
    print("=" * 50)
    print()
    print("需要 Telegram API 凭证，请从 https://my.telegram.org 获取")
    print()

    api_id = input("请输入 API_ID: ").strip()
    api_hash = input("请输入 API_HASH: ").strip()

    if not api_id or not api_hash:
        print("错误: API_ID 和 API_HASH 不能为空")
        sys.exit(1)

    # 保存到配置目录
    env_path = CONFIG_DIR / ".env"
    env_path.write_text(f"TELEGRAM_API_ID={api_id}\nTELEGRAM_API_HASH={api_hash}\n")
    print(f"\n配置已保存到: {env_path}")

    return int(api_id), api_hash


async def do_login(api_id: int, api_hash: str):
    """执行登录流程"""
    session_path = get_session_path()
    client = TelegramClient(session_path, api_id, api_hash)

    print("\n正在连接 Telegram...")
    await client.start()

    me = await client.get_me()
    print()
    print("=" * 50)
    print("登录成功!")
    print("=" * 50)
    print(f"  账号: {me.first_name} {me.last_name or ''}")
    print(f"  用户名: @{me.username}")
    print(f"  手机号: {me.phone}")
    print()
    print(f"Session 已保存到: {session_path}.session")
    print()
    print("现在可以在 Claude Code 中使用 Telegram MCP 了")

    await client.disconnect()


def login():
    """登录命令入口"""
    print()

    # 检查是否需要配置
    if is_configured():
        api_id, api_hash = API_ID, API_HASH
        print(f"使用现有配置 (API_ID: {api_id})")
    else:
        api_id, api_hash = setup_env()

    # 执行登录
    asyncio.run(do_login(api_id, api_hash))


async def check_status():
    """检查 session 状态"""
    print()
    print("=" * 50)
    print("Telegram MCP 状态检查")
    print("=" * 50)
    print()

    # 配置检查
    print(f"配置目录: {CONFIG_DIR}")
    print(f"配置文件: {ENV_FILE}")
    print(f"API 配置: {'已配置' if is_configured() else '未配置'}")
    print()

    # Session 检查
    session_file = Path(get_session_path() + ".session")
    print(f"Session 文件: {session_file}")
    print(f"Session 状态: {'存在' if session_file.exists() else '不存在'}")

    if not has_session():
        print()
        print("提示: 运行 telegram-mcp-login 进行登录")
        return

    if not is_configured():
        print()
        print("提示: 运行 telegram-mcp-login 配置 API 凭证")
        return

    # 验证 session 是否有效
    print()
    print("正在验证 session...")

    try:
        client = TelegramClient(get_session_path(), API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            print()
            print("Session 有效!")
            print(f"  账号: {me.first_name} {me.last_name or ''}")
            print(f"  用户名: @{me.username}")
        else:
            print()
            print("Session 已过期，请运行 telegram-mcp-login 重新登录")

        await client.disconnect()
    except Exception as e:
        print(f"验证失败: {e}")
        print("请运行 telegram-mcp-login 重新登录")


def status():
    """状态检查命令入口"""
    asyncio.run(check_status())


# ========== 缓存管理命令 ==========

def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


async def show_cache_stats():
    """显示缓存统计信息"""
    from . import cache

    await cache.init_cache()
    stats = await cache.get_cache_stats()
    await cache.close_db()

    print()
    print("=" * 50)
    print("Telegram MCP 缓存统计")
    print("=" * 50)
    print()
    print(f"数据库路径: {stats['db_path']}")
    print(f"数据库大小: {format_size(stats['db_size_bytes'])}")
    print(f"下载目录:   {stats['download_dir']}")
    print()
    print("--- 名称映射缓存 ---")
    print(f"  缓存条目: {stats['alias_count']} 条")
    print()
    print("--- 媒体路径缓存 ---")
    print(f"  缓存条目: {stats['media_count']} 条")
    print(f"  记录大小: {format_size(stats['media_size_bytes'])}")
    print(f"  实际占用: {format_size(stats['actual_disk_bytes'])}")
    print()
    print("--- 容量限制 ---")
    print(f"  最大容量: {format_size(stats['max_cache_size'])}")
    usage_pct = (stats['media_size_bytes'] / stats['max_cache_size'] * 100) if stats['max_cache_size'] > 0 else 0
    print(f"  使用率:   {usage_pct:.1f}%")
    print()


def cache_stats():
    """缓存统计命令入口"""
    asyncio.run(show_cache_stats())


async def do_cache_clear(clear_type: str, delete_files: bool):
    """执行缓存清理"""
    from . import cache

    await cache.init_cache()

    # 清理前统计
    stats_before = await cache.get_cache_stats()

    if clear_type == "all":
        await cache.clear_all_cache(delete_files=delete_files)
        print(f"已清空所有缓存")
        print(f"  - 名称映射: {stats_before['alias_count']} 条")
        print(f"  - 媒体缓存: {stats_before['media_count']} 条")
    elif clear_type == "media":
        await cache.clear_media_cache(delete_files=delete_files)
        print(f"已清空媒体缓存: {stats_before['media_count']} 条")
    elif clear_type == "alias":
        await cache.clear_alias_cache()
        print(f"已清空名称映射: {stats_before['alias_count']} 条")

    if delete_files:
        print(f"已删除媒体文件: {format_size(stats_before['actual_disk_bytes'])}")

    await cache.close_db()


def cache_clear():
    """缓存清理命令入口"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="telegram-mcp-cache-clear",
        description="清理 Telegram MCP 缓存"
    )
    parser.add_argument(
        "type",
        nargs="?",
        choices=["all", "media", "alias"],
        default="all",
        help="清理类型: all(全部), media(媒体), alias(名称映射)"
    )
    parser.add_argument(
        "--delete-files",
        action="store_true",
        help="同时删除下载的媒体文件"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="跳过确认提示"
    )

    args = parser.parse_args()

    # 确认提示
    if not args.yes:
        msg = f"确定要清空 {args.type} 缓存吗？"
        if args.delete_files:
            msg += "（包括媒体文件）"
        confirm = input(f"{msg} [y/N]: ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    print()
    asyncio.run(do_cache_clear(args.type, args.delete_files))
    print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            status()
        elif cmd == "cache-stats":
            cache_stats()
        elif cmd == "cache-clear":
            sys.argv = sys.argv[1:]  # 移除子命令
            cache_clear()
        else:
            login()
    else:
        login()
