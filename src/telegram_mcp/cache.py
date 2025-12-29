"""SQLite 缓存模块 - 名称映射 + 媒体路径"""

import aiosqlite
import os
from pathlib import Path
from .config import CONFIG_DIR, DOWNLOAD_DIR

# 缓存数据库路径
CACHE_DB = CONFIG_DIR / "cache.db"

# 缓存容量上限（字节）- 默认 500MB
try:
    MAX_CACHE_SIZE = int(os.getenv("TELEGRAM_CACHE_MAX_SIZE", 500 * 1024 * 1024))
except ValueError:
    MAX_CACHE_SIZE = 500 * 1024 * 1024

# 淘汰时保留的目标容量（80%）
TARGET_CACHE_SIZE = int(MAX_CACHE_SIZE * 0.8)

# 连接池（复用连接）
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（复用单一连接）"""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(CACHE_DB, timeout=30.0)
        _db.row_factory = aiosqlite.Row
        # 启用 WAL 模式，提升并发性能
        await _db.execute("PRAGMA journal_mode=WAL")
        # 设置 busy_timeout，防止锁定错误
        await _db.execute("PRAGMA busy_timeout=30000")
    return _db


async def close_db():
    """关闭数据库连接"""
    global _db
    if _db:
        await _db.close()
        _db = None


async def init_cache():
    """初始化缓存表结构"""
    db = await get_db()
    # 名称映射表：alias(名称/@username) → chat_id
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_alias (
            alias TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            updated_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """)
    # 媒体路径表：(chat_id, msg_id) → local_path
    await db.execute("""
        CREATE TABLE IF NOT EXISTS media_cache (
            chat_id INTEGER NOT NULL,
            msg_id INTEGER NOT NULL,
            local_path TEXT NOT NULL,
            file_size INTEGER,
            cached_at INTEGER DEFAULT (strftime('%s', 'now')),
            PRIMARY KEY (chat_id, msg_id)
        )
    """)
    # 创建索引加速查询
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_media_chat ON media_cache(chat_id)
    """)
    await db.commit()


# ========== 名称映射缓存 ==========

async def get_chat_id(alias: str) -> int | None:
    """从缓存获取 chat_id"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT chat_id FROM chat_alias WHERE alias = ?",
        (alias,)
    )
    row = await cursor.fetchone()
    return row["chat_id"] if row else None


async def set_chat_alias(alias: str, chat_id: int):
    """缓存单个名称映射"""
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO chat_alias (alias, chat_id, updated_at) VALUES (?, ?, strftime('%s', 'now'))",
        (alias, chat_id)
    )
    await db.commit()


async def set_chat_aliases_batch(mappings: list[tuple[str, int]]):
    """批量缓存名称映射"""
    if not mappings:
        return
    db = await get_db()
    await db.executemany(
        "INSERT OR REPLACE INTO chat_alias (alias, chat_id, updated_at) VALUES (?, ?, strftime('%s', 'now'))",
        mappings
    )
    await db.commit()


async def delete_chat_alias(alias: str):
    """删除失效的映射"""
    db = await get_db()
    await db.execute("DELETE FROM chat_alias WHERE alias = ?", (alias,))
    await db.commit()


# ========== 媒体路径缓存 ==========

async def get_media_path(chat_id: int, msg_id: int) -> str | None:
    """获取已下载媒体的本地路径"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT local_path FROM media_cache WHERE chat_id = ? AND msg_id = ?",
        (chat_id, msg_id)
    )
    row = await cursor.fetchone()
    if row:
        path = Path(row["local_path"])
        if path.exists():
            return str(path)
        # 文件不存在，清理脏数据
        await delete_media_cache(chat_id, msg_id)
    return None


async def set_media_path(chat_id: int, msg_id: int, local_path: str, file_size: int | None = None):
    """缓存媒体下载路径"""
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO media_cache
           (chat_id, msg_id, local_path, file_size, cached_at)
           VALUES (?, ?, ?, ?, strftime('%s', 'now'))""",
        (chat_id, msg_id, local_path, file_size)
    )
    await db.commit()


async def delete_media_cache(chat_id: int, msg_id: int):
    """删除媒体缓存记录"""
    db = await get_db()
    await db.execute(
        "DELETE FROM media_cache WHERE chat_id = ? AND msg_id = ?",
        (chat_id, msg_id)
    )
    await db.commit()


# ========== 统计与清理 ==========

async def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    db = await get_db()
    alias_cursor = await db.execute("SELECT COUNT(*) FROM chat_alias")
    media_cursor = await db.execute("SELECT COUNT(*) FROM media_cache")
    size_cursor = await db.execute("SELECT COALESCE(SUM(file_size), 0) FROM media_cache")

    # 计算实际磁盘占用（扫描下载目录）
    actual_disk_size = 0
    if DOWNLOAD_DIR.exists():
        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file():
                actual_disk_size += f.stat().st_size

    # 数据库文件大小
    db_size = CACHE_DB.stat().st_size if CACHE_DB.exists() else 0

    return {
        "alias_count": (await alias_cursor.fetchone())[0],
        "media_count": (await media_cursor.fetchone())[0],
        "media_size_bytes": (await size_cursor.fetchone())[0],
        "actual_disk_bytes": actual_disk_size,
        "db_size_bytes": db_size,
        "max_cache_size": MAX_CACHE_SIZE,
        "db_path": str(CACHE_DB),
        "download_dir": str(DOWNLOAD_DIR)
    }


async def clear_all_cache(delete_files: bool = False):
    """清空所有缓存

    Args:
        delete_files: 是否同时删除下载的媒体文件
    """
    db = await get_db()

    if delete_files:
        # 获取所有缓存的文件路径
        cursor = await db.execute("SELECT local_path FROM media_cache")
        rows = await cursor.fetchall()
        for row in rows:
            path = Path(row["local_path"])
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    await db.execute("DELETE FROM chat_alias")
    await db.execute("DELETE FROM media_cache")
    await db.commit()


async def clear_media_cache(delete_files: bool = False):
    """仅清空媒体缓存"""
    db = await get_db()

    if delete_files:
        cursor = await db.execute("SELECT local_path FROM media_cache")
        rows = await cursor.fetchall()
        for row in rows:
            path = Path(row["local_path"])
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    await db.execute("DELETE FROM media_cache")
    await db.commit()


async def clear_alias_cache():
    """仅清空名称映射缓存"""
    db = await get_db()
    await db.execute("DELETE FROM chat_alias")
    await db.commit()


# ========== LRU 淘汰策略 ==========

async def get_total_media_size() -> int:
    """获取媒体缓存总大小"""
    db = await get_db()
    cursor = await db.execute("SELECT COALESCE(SUM(file_size), 0) FROM media_cache")
    return (await cursor.fetchone())[0]


async def evict_lru(target_size: int | None = None):
    """LRU 淘汰：删除最久未使用的缓存直到低于目标大小

    Args:
        target_size: 目标大小（字节），默认为 TARGET_CACHE_SIZE
    """
    if target_size is None:
        target_size = TARGET_CACHE_SIZE

    db = await get_db()
    current_size = await get_total_media_size()

    if current_size <= target_size:
        return 0  # 无需淘汰

    # 按 cached_at 升序获取（最旧的优先删除）
    cursor = await db.execute("""
        SELECT chat_id, msg_id, local_path, file_size
        FROM media_cache
        ORDER BY cached_at ASC
    """)
    rows = await cursor.fetchall()

    evicted_count = 0
    evicted_size = 0

    for row in rows:
        if current_size - evicted_size <= target_size:
            break

        chat_id, msg_id = row["chat_id"], row["msg_id"]
        local_path = row["local_path"]
        file_size = row["file_size"] or 0

        # 删除文件
        path = Path(local_path)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

        # 删除数据库记录
        await db.execute(
            "DELETE FROM media_cache WHERE chat_id = ? AND msg_id = ?",
            (chat_id, msg_id)
        )

        evicted_size += file_size
        evicted_count += 1

    await db.commit()
    return evicted_count


async def maybe_evict():
    """检查是否需要淘汰，如需要则执行 LRU 淘汰"""
    current_size = await get_total_media_size()
    if current_size > MAX_CACHE_SIZE:
        return await evict_lru()
    return 0


async def update_access_time(chat_id: int, msg_id: int):
    """更新缓存访问时间（用于 LRU）"""
    db = await get_db()
    await db.execute(
        "UPDATE media_cache SET cached_at = strftime('%s', 'now') WHERE chat_id = ? AND msg_id = ?",
        (chat_id, msg_id)
    )
    await db.commit()
