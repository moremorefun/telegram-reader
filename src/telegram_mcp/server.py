#!/usr/bin/env python3
"""
Telegram MCP Server
让 Claude 直接读取 Telegram 消息
"""

import asyncio
import json
import sys
import fcntl
from datetime import datetime, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from .config import API_ID, API_HASH, get_session_path, is_configured, has_session, CONFIG_DIR
from . import cache

# 锁文件路径
LOCK_FILE = CONFIG_DIR / "server.lock"


async def resolve_chat(tg: TelegramClient, chat: int | str) -> int:
    """解析聊天标识，支持 ID、名称、用户名"""
    # 如果是整数，直接返回
    if isinstance(chat, int):
        return chat

    # 如果是字符串数字，转换为整数
    if isinstance(chat, str) and chat.lstrip('-').isdigit():
        return int(chat)

    # 尝试从 SQLite 缓存获取
    cached_id = await cache.get_chat_id(chat)
    if cached_id:
        return cached_id

    # 如果是 @username 格式，直接使用 Telethon 解析
    if chat.startswith('@'):
        entity = await tg.get_entity(chat)
        await cache.set_chat_alias(chat, entity.id)
        return entity.id

    # 遍历对话列表匹配名称
    mappings = []
    matched_id = None
    async for dialog in tg.iter_dialogs():
        mappings.append((dialog.name, dialog.id))
        if dialog.name == chat and matched_id is None:
            matched_id = dialog.id

    # 批量写入缓存
    await cache.set_chat_aliases_batch(mappings)

    if matched_id:
        return matched_id

    raise ValueError(f"找不到对话: {chat}")

# 全局客户端
client: TelegramClient | None = None
# 全局锁文件句柄
_lock_fd = None


def acquire_lock() -> bool:
    """获取独占锁，防止多实例运行"""
    global _lock_fd
    try:
        _lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(asyncio.current_task().get_name() if asyncio.current_task() else 'main'))
        _lock_fd.flush()
        return True
    except (IOError, OSError):
        return False


def release_lock():
    """释放锁"""
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            pass
        _lock_fd = None


async def get_client() -> TelegramClient:
    """获取或创建 Telegram 客户端"""
    global client
    if client is None or not client.is_connected():
        client = TelegramClient(get_session_path(), API_ID, API_HASH)
        await client.start()
    return client


async def close_client():
    """关闭 Telegram 客户端"""
    global client
    if client:
        await client.disconnect()
        client = None


# 创建 MCP 服务器
server = Server("telegram-reader")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用工具"""
    return [
        Tool(
            name="telegram_dialogs",
            description="获取 Telegram 对话列表(群组、频道、私聊)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最大数量,默认 50",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="telegram_messages",
            description="获取指定群组/对话的消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": ["integer", "string"],
                        "description": "群组/对话标识：可以是 ID(如 -1003549587777)、名称(如 '钓鱼翁')或用户名(如 '@username')"
                    },
                    "from_user": {
                        "type": "string",
                        "description": "只获取特定用户的消息(用户名或ID)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大消息数,默认 50",
                        "default": 50
                    },
                    "days": {
                        "type": "integer",
                        "description": "只获取最近 N 天的消息"
                    },
                    "media_only": {
                        "type": "boolean",
                        "description": "只返回带媒体的消息",
                        "default": False
                    }
                },
                "required": ["chat_id"]
            }
        ),
        Tool(
            name="telegram_download",
            description="下载消息中的媒体文件(图片、文档等)",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": ["integer", "string"],
                        "description": "群组/对话标识：可以是 ID、名称或用户名"
                    },
                    "message_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "消息 ID 列表"
                    }
                },
                "required": ["chat_id", "message_ids"]
            }
        ),
        Tool(
            name="telegram_search",
            description="在群组中搜索消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": ["integer", "string"],
                        "description": "群组/对话标识：可以是 ID、名称或用户名"
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大结果数,默认 20",
                        "default": 20
                    }
                },
                "required": ["chat_id", "query"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    """执行工具调用"""
    tg = await get_client()

    if name == "telegram_dialogs":
        limit = arguments.get("limit", 50)
        dialogs = []
        mappings = []
        async for dialog in tg.iter_dialogs(limit=limit):
            mappings.append((dialog.name, dialog.id))
            dialogs.append({
                "id": dialog.id,
                "name": dialog.name,
                "type": "群组" if dialog.is_group else ("频道" if dialog.is_channel else "私聊"),
                "unread": dialog.unread_count
            })
        # 批量写入缓存
        await cache.set_chat_aliases_batch(mappings)
        return [TextContent(type="text", text=json.dumps(dialogs, ensure_ascii=False, indent=2))]

    elif name == "telegram_messages":
        chat_id = await resolve_chat(tg, arguments["chat_id"])
        from_user = arguments.get("from_user")
        limit = arguments.get("limit", 50)
        days = arguments.get("days")
        media_only = arguments.get("media_only", False)

        offset_date = None
        if days:
            offset_date = datetime.now() - timedelta(days=days)

        messages = []
        async for message in tg.iter_messages(
            chat_id,
            limit=limit,
            from_user=from_user,
            offset_date=offset_date
        ):
            has_media = message.media is not None
            if media_only and not has_media:
                continue

            msg_data = {
                "id": message.id,
                "date": message.date.strftime("%Y-%m-%d %H:%M") if message.date else None,
                "sender": None,
                "forward_from": None,
                "forward_date": None,
                "text": message.text or "",
                "has_media": has_media,
                "media_type": None
            }

            if message.sender:
                if hasattr(message.sender, "first_name"):
                    msg_data["sender"] = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                elif hasattr(message.sender, "title"):
                    msg_data["sender"] = message.sender.title

            # 获取转发消息的原始发送者
            if message.forward:
                fwd = message.forward
                # 优先使用 from_name（隐私保护时仍可能有值）
                if fwd.from_name:
                    msg_data["forward_from"] = fwd.from_name
                # 尝试从 from_id 获取完整用户/频道信息
                elif fwd.from_id:
                    try:
                        entity = await tg.get_entity(fwd.from_id)
                        if hasattr(entity, "first_name"):
                            msg_data["forward_from"] = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                        elif hasattr(entity, "title"):
                            msg_data["forward_from"] = entity.title
                    except Exception:
                        msg_data["forward_from"] = str(fwd.from_id)
                if fwd.date:
                    msg_data["forward_date"] = fwd.date.strftime("%Y-%m-%d %H:%M")

            if message.media:
                if isinstance(message.media, MessageMediaPhoto):
                    msg_data["media_type"] = "photo"
                elif isinstance(message.media, MessageMediaDocument):
                    msg_data["media_type"] = "document"
                else:
                    msg_data["media_type"] = type(message.media).__name__

            messages.append(msg_data)

        return [TextContent(type="text", text=json.dumps(messages, ensure_ascii=False, indent=2))]

    elif name == "telegram_download":
        chat_id = await resolve_chat(tg, arguments["chat_id"])
        message_ids = arguments["message_ids"]

        from .config import DOWNLOAD_DIR
        from pathlib import Path
        download_dir = DOWNLOAD_DIR

        results = []
        for msg_id in message_ids:
            # 检查缓存
            cached_path = await cache.get_media_path(chat_id, msg_id)
            if cached_path:
                # 更新访问时间（LRU）
                await cache.update_access_time(chat_id, msg_id)
                results.append({
                    "id": msg_id,
                    "path": cached_path,
                    "success": True,
                    "cached": True
                })
                continue

            # 缓存未命中，下载媒体
            message = await tg.get_messages(chat_id, ids=msg_id)
            if message and message.media:
                path = await message.download_media(file=str(download_dir))
                if path:
                    # 写入缓存
                    file_size = None
                    try:
                        file_size = Path(path).stat().st_size
                    except OSError:
                        pass
                    await cache.set_media_path(chat_id, msg_id, path, file_size)
                    # 检查是否需要 LRU 淘汰
                    await cache.maybe_evict()
                results.append({"id": msg_id, "path": path, "success": True, "cached": False})
            else:
                results.append({"id": msg_id, "path": None, "success": False})

        return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

    elif name == "telegram_search":
        chat_id = await resolve_chat(tg, arguments["chat_id"])
        query = arguments["query"]
        limit = arguments.get("limit", 20)

        messages = []
        async for message in tg.iter_messages(chat_id, search=query, limit=limit):
            msg_data = {
                "id": message.id,
                "date": message.date.strftime("%Y-%m-%d %H:%M") if message.date else None,
                "sender": None,
                "forward_from": None,
                "forward_date": None,
                "text": message.text or "",
                "has_media": message.media is not None
            }

            if message.sender:
                if hasattr(message.sender, "first_name"):
                    msg_data["sender"] = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()

            # 获取转发消息的原始发送者
            if message.forward:
                fwd = message.forward
                # 优先使用 from_name（隐私保护时仍可能有值）
                if fwd.from_name:
                    msg_data["forward_from"] = fwd.from_name
                # 尝试从 from_id 获取完整用户/频道信息
                elif fwd.from_id:
                    try:
                        entity = await tg.get_entity(fwd.from_id)
                        if hasattr(entity, "first_name"):
                            msg_data["forward_from"] = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                        elif hasattr(entity, "title"):
                            msg_data["forward_from"] = entity.title
                    except Exception:
                        msg_data["forward_from"] = str(fwd.from_id)
                if fwd.date:
                    msg_data["forward_date"] = fwd.date.strftime("%Y-%m-%d %H:%M")

            messages.append(msg_data)

        return [TextContent(type="text", text=json.dumps(messages, ensure_ascii=False, indent=2))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_server():
    """运行 MCP 服务器"""
    # 检查配置
    if not is_configured():
        print("错误: 未配置 Telegram API 凭证", file=sys.stderr)
        print("请运行 telegram-mcp-login 进行配置", file=sys.stderr)
        sys.exit(1)

    if not has_session():
        print("错误: 未找到登录 session", file=sys.stderr)
        print("请运行 telegram-mcp-login 进行登录", file=sys.stderr)
        sys.exit(1)

    # 尝试获取锁
    if not acquire_lock():
        print("错误: 另一个 telegram-mcp 实例正在运行", file=sys.stderr)
        print("请先停止其他实例，或删除锁文件: " + str(LOCK_FILE), file=sys.stderr)
        sys.exit(1)

    try:
        # 初始化缓存
        await cache.init_cache()

        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # 清理资源
        await close_client()
        await cache.close_db()
        release_lock()


def main():
    """入口函数"""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
