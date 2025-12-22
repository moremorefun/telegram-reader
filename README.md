# Telegram MCP Server

让 Claude Code 读取 Telegram 消息的 MCP 服务器。

[![PyPI](https://img.shields.io/pypi/v/telegram-reader-mcp)](https://pypi.org/project/telegram-reader-mcp/)

## 功能

- `telegram_dialogs` - 获取对话列表（群组、频道、私聊）
- `telegram_messages` - 获取指定对话的消息
- `telegram_search` - 搜索消息
- `telegram_download` - 下载媒体文件（支持缓存，避免重复下载）

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
- `TELEGRAM_CACHE_MAX_SIZE` - 媒体缓存容量上限（字节），默认 500MB

获取自己的 API 凭证：https://my.telegram.org → API development tools

重启 Claude Code 后即可使用。

## 使用示例

在 Claude Code 中可以这样问：

- "获取我的 Telegram 对话列表"
- "读取 XXX 群组的最近消息"
- "在 XXX 群组中搜索 关键词"
- "下载这条消息的图片"

## 缓存管理

本工具使用 SQLite 缓存来提升性能：

- **名称映射缓存**：对话名称 → ID 映射，避免重复遍历对话列表
- **媒体路径缓存**：已下载文件的路径，避免重复下载
- **LRU 淘汰策略**：超过容量上限时自动清理最久未使用的缓存

### 查看缓存统计

```bash
uvx --from telegram-reader-mcp telegram-mcp-cache-stats
```

示例输出：
```
==================================================
Telegram MCP 缓存统计
==================================================

数据库路径: /Users/xxx/.config/telegram-mcp/cache.db
数据库大小: 24.0 KB
下载目录:   /Users/xxx/.config/telegram-mcp/downloads

--- 名称映射缓存 ---
  缓存条目: 50 条

--- 媒体路径缓存 ---
  缓存条目: 10 条
  记录大小: 150.0 MB
  实际占用: 150.0 MB

--- 容量限制 ---
  最大容量: 500.0 MB
  使用率:   30.0%
```

### 清理缓存

```bash
# 清空所有缓存（需确认）
uvx --from telegram-reader-mcp telegram-mcp-cache-clear

# 仅清空媒体缓存
uvx --from telegram-reader-mcp telegram-mcp-cache-clear media

# 仅清空名称映射缓存
uvx --from telegram-reader-mcp telegram-mcp-cache-clear alias

# 跳过确认
uvx --from telegram-reader-mcp telegram-mcp-cache-clear -y

# 同时删除已下载的媒体文件
uvx --from telegram-reader-mcp telegram-mcp-cache-clear media --delete-files -y
```

## 文件结构

```
~/.config/telegram-mcp/
├── session.session   # Telegram 登录态
├── .env              # API 凭证配置
├── cache.db          # SQLite 缓存数据库
└── downloads/        # 媒体文件下载目录
```

## 注意事项

- Session 文件 (`~/.config/telegram-mcp/session.session`) 保存登录状态，删除后需重新登录
- 内置公共 API 可能因使用人数多而受限，建议申请自己的 API 凭证
- 缓存数据库和下载文件会占用磁盘空间，可通过 `telegram-mcp-cache-clear` 清理
