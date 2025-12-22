"""配置管理"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 配置目录：~/.config/telegram-mcp/
CONFIG_DIR = Path.home() / ".config" / "telegram-mcp"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Session 文件路径
SESSION_PATH = CONFIG_DIR / "session"

# .env 文件路径（优先使用配置目录，其次使用项目目录）
ENV_FILE = CONFIG_DIR / ".env"
if not ENV_FILE.exists():
    # 兼容旧的项目目录 .env
    project_env = Path(__file__).parent.parent.parent / ".env"
    if project_env.exists():
        ENV_FILE = project_env

load_dotenv(ENV_FILE)

# Telegram API 配置（默认使用 PagerMaid 公共 API）
DEFAULT_API_ID = 21724
DEFAULT_API_HASH = "3e0cb5efcd52300aec5994fdfc5bdc16"

API_ID = int(os.getenv("TELEGRAM_API_ID", "0")) or DEFAULT_API_ID
API_HASH = os.getenv("TELEGRAM_API_HASH", "") or DEFAULT_API_HASH

# 下载目录
_download_dir_env = os.getenv("TELEGRAM_DOWNLOAD_DIR", "").strip()
DOWNLOAD_DIR = Path(_download_dir_env) if _download_dir_env else (CONFIG_DIR / "downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_session_path() -> str:
    """获取 session 文件路径（不含扩展名）"""
    return str(SESSION_PATH)


def is_configured() -> bool:
    """检查是否已配置 API 凭证（有默认值，总是返回 True）"""
    return API_ID != 0 and API_HASH != ""


def is_using_default() -> bool:
    """检查是否使用默认 API 凭证"""
    return API_ID == DEFAULT_API_ID and API_HASH == DEFAULT_API_HASH


def has_session() -> bool:
    """检查是否存在 session 文件"""
    session_file = Path(str(SESSION_PATH) + ".session")
    return session_file.exists()
