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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status()
    else:
        login()
