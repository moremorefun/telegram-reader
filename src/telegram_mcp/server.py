#!/usr/bin/env python3
"""
Telegram MCP Server
让 Claude 直接读取 Telegram 消息
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from .config import API_ID, API_HASH, get_session_path, is_configured, has_session

# 全局客户端
client: TelegramClient | None = None


async def get_client() -> TelegramClient:
    """获取或创建 Telegram 客户端"""
    global client
    if client is None or not client.is_connected():
        client = TelegramClient(get_session_path(), API_ID, API_HASH)
        await client.start()
    return client


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
                        "type": "integer",
                        "description": "群组/对话 ID(如 -1003549587777)"
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
                        "type": "integer",
                        "description": "群组/对话 ID"
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
                        "type": "integer",
                        "description": "群组/对话 ID"
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
        async for dialog in tg.iter_dialogs(limit=limit):
            dialogs.append({
                "id": dialog.id,
                "name": dialog.name,
                "type": "群组" if dialog.is_group else ("频道" if dialog.is_channel else "私聊"),
                "unread": dialog.unread_count
            })
        return [TextContent(type="text", text=json.dumps(dialogs, ensure_ascii=False, indent=2))]

    elif name == "telegram_messages":
        chat_id = arguments["chat_id"]
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
                "text": message.text or "",
                "has_media": has_media,
                "media_type": None
            }

            if message.sender:
                if hasattr(message.sender, "first_name"):
                    msg_data["sender"] = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                elif hasattr(message.sender, "title"):
                    msg_data["sender"] = message.sender.title

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
        chat_id = arguments["chat_id"]
        message_ids = arguments["message_ids"]

        from .config import DOWNLOAD_DIR
        download_dir = DOWNLOAD_DIR

        results = []
        for msg_id in message_ids:
            message = await tg.get_messages(chat_id, ids=msg_id)
            if message and message.media:
                path = await message.download_media(file=str(download_dir))
                results.append({"id": msg_id, "path": path, "success": True})
            else:
                results.append({"id": msg_id, "path": None, "success": False})

        return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

    elif name == "telegram_search":
        chat_id = arguments["chat_id"]
        query = arguments["query"]
        limit = arguments.get("limit", 20)

        messages = []
        async for message in tg.iter_messages(chat_id, search=query, limit=limit):
            msg_data = {
                "id": message.id,
                "date": message.date.strftime("%Y-%m-%d %H:%M") if message.date else None,
                "sender": None,
                "text": message.text or "",
                "has_media": message.media is not None
            }

            if message.sender:
                if hasattr(message.sender, "first_name"):
                    msg_data["sender"] = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()

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

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """入口函数"""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
