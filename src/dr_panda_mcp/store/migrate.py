"""启动迁移与 SQLite 备份（planning 5.5）。

迁移脚本放在 ``store/alembic/``，进程启动时升级到最新版本；SQLite 在迁移前
把数据库文件复制到 ``<db 目录>/backup/``，保留最近 5 份。
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncEngine

from dr_panda_mcp.store.url import database_path

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backup"
BACKUP_KEEP = 5
ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"


def backup_sqlite_database(url: str, *, keep: int = BACKUP_KEEP) -> Path | None:
    """SQLite 迁移前备份；内存库或空文件返回 ``None``。"""
    source = database_path(url)
    if source is None or not source.exists() or source.stat().st_size == 0:
        return None

    backup_dir = source.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"{stamp}.sqlite"

    # SQLite 的 backup API 会正确包含 WAL 中尚未 checkpoint 的已提交事务；
    # 直接 copy2 主文件在 WAL 模式下可能得到不完整备份。
    source_connection = sqlite3.connect(source)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    # 备份文件按 mtime 排序；这里改成当前时间，避免沿用源库 mtime 被误判为旧
    os.utime(target, None)
    _prune_backups(backup_dir, keep)
    return target


def _prune_backups(backup_dir: Path, keep: int) -> None:
    backups = sorted(
        backup_dir.glob("*.sqlite"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:  # pragma: no cover - 清理失败不影响启动
            logger.warning("清理旧备份失败：%s", old)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def upgrade_to_head(sync_connection) -> None:
    """在已有同步连接上执行 Alembic 升级（由异步引擎的 run_sync 调用）。"""
    config = _alembic_config()
    config.attributes["connection"] = sync_connection
    command.upgrade(config, "head")


async def migrate(engine: AsyncEngine) -> Path | None:
    """备份（仅 SQLite）后迁移到最新版本，返回备份文件路径。"""
    backup = backup_sqlite_database(str(engine.url))
    if backup is not None:
        logger.info("迁移前已备份 SQLite：%s", backup)
    async with engine.begin() as connection:
        await connection.run_sync(upgrade_to_head)
    return backup
