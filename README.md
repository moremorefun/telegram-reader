# Telegram MCP Server

让 Claude Code 读取 Telegram 消息的 MCP 服务器。

## 功能

- `telegram_dialogs` - 获取对话列表（群组、频道、私聊）
- `telegram_messages` - 获取指定对话的消息
- `telegram_search` - 搜索消息
- `telegram_download` - 下载媒体文件

## 安装

```bash
cd telegram-reader
uv sync
```

## 配置

### 1. API 凭证（可选）

项目内置了默认的公共 API 凭证，开箱即用，无需配置。

如需使用自己的 API 凭证（推荐），创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env`：

```
TELEGRAM_API_ID=你的api_id
TELEGRAM_API_HASH=你的api_hash
```

获取方式：访问 https://my.telegram.org → API development tools

### 2. 登录 Telegram

首次使用需要登录：

```bash
uv run telegram-mcp-login
```

按提示输入手机号和验证码，登录成功后会生成 session 文件。

检查登录状态：

```bash
uv run telegram-mcp-status
```

## 在 Claude Code 中使用

编辑 `~/.claude/mcp.json` 或项目目录下的 `.mcp.json`：

```json
{
  "mcpServers": {
    "telegram": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/telegram-reader",
        "telegram-mcp"
      ],
      "env": {
        "TELEGRAM_API_ID": "your_api_id",
        "TELEGRAM_API_HASH": "your_api_hash",
        "TELEGRAM_DOWNLOAD_DIR": "/path/to/downloads"
      }
    }
  }
}
```

环境变量说明：
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` - API 凭证（可选，有默认值）
- `TELEGRAM_DOWNLOAD_DIR` - 下载目录（可选，默认 `~/.config/telegram-mcp/downloads`）

重启 Claude Code 后即可使用。

## 使用示例

在 Claude Code 中可以这样问：

- "获取我的 Telegram 对话列表"
- "读取 XXX 群组的最近消息"
- "在 XXX 群组中搜索 关键词"
- "下载这条消息的图片"

## 文件说明

```
telegram-reader/
├── .env              # API 凭证配置
├── src/telegram_mcp/ # 源代码
├── downloads/        # 下载的媒体文件
└── *.session         # Telegram 登录会话（自动生成）
```

## 注意事项

- `.env` 和 `*.session` 文件包含敏感信息，已在 `.gitignore` 中排除
- Session 文件保存登录状态，删除后需重新登录
- API 凭证是个人的，不要分享给他人
