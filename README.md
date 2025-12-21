# Telegram MCP Server

让 Claude Code 读取 Telegram 消息的 MCP 服务器。

[![PyPI](https://img.shields.io/pypi/v/telegram-reader-mcp)](https://pypi.org/project/telegram-reader-mcp/)

## 功能

- `telegram_dialogs` - 获取对话列表（群组、频道、私聊）
- `telegram_messages` - 获取指定对话的消息
- `telegram_search` - 搜索消息
- `telegram_download` - 下载媒体文件

## 安装

```bash
# 使用 uvx（推荐）
uvx --from telegram-reader-mcp telegram-mcp

# 或从源码安装
git clone https://github.com/moremorefun/telegram-reader.git
cd telegram-reader
uv sync
```

## 配置

### 登录 Telegram

首次使用需要登录：

```bash
uvx --from telegram-reader-mcp telegram-mcp-login
```

按提示输入手机号和验证码，登录成功后会在 `~/.config/telegram-mcp/` 生成 session 文件。

检查登录状态：

```bash
uvx --from telegram-reader-mcp telegram-mcp-status
```

示例输出：
```
==================================================
Telegram MCP 状态检查
==================================================

配置目录: ~/.config/telegram-mcp
Session 状态: 存在

正在验证 session...

Session 有效!
  账号: Your Name
  用户名: @your_username
```

## 在 Claude Code 中使用

编辑 `~/.claude/mcp.json` 或项目目录下的 `.mcp.json`：

```json
{
  "mcpServers": {
    "telegram": {
      "command": "uvx",
      "args": ["--from", "telegram-reader-mcp", "telegram-mcp"],
      "env": {
        "TELEGRAM_API_ID": "your_api_id",
        "TELEGRAM_API_HASH": "your_api_hash",
        "TELEGRAM_DOWNLOAD_DIR": "/path/to/downloads"
      }
    }
  }
}
```

环境变量（均为可选）：
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` - API 凭证，有内置默认值
- `TELEGRAM_DOWNLOAD_DIR` - 下载目录，默认 `~/.config/telegram-mcp/downloads`

获取自己的 API 凭证：https://my.telegram.org → API development tools

重启 Claude Code 后即可使用。

## 使用示例

在 Claude Code 中可以这样问：

- "获取我的 Telegram 对话列表"
- "读取 XXX 群组的最近消息"
- "在 XXX 群组中搜索 关键词"
- "下载这条消息的图片"

## 注意事项

- Session 文件 (`~/.config/telegram-mcp/session.session`) 保存登录状态，删除后需重新登录
- 内置公共 API 可能因使用人数多而受限，建议申请自己的 API 凭证
