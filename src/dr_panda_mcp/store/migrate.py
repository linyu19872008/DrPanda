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
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import String, column, select, table
from sqlalchemy.ext.asyncio import AsyncEngine

from dr_panda_mcp.log import format_event
from dr_panda_mcp.store.url import database_path

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backup"
BACKUP_KEEP = 20
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
            logger.warning("failed to remove an old backup: %s", old)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def upgrade_to_head(sync_connection) -> None:
    """在已有同步连接上执行 Alembic 升级（由异步引擎的 run_sync 调用）。"""
    config = _alembic_config()
    config.attributes["connection"] = sync_connection
    command.upgrade(config, "head")


async def _has_pending_migrations(engine: AsyncEngine) -> bool:
    async with engine.connect() as connection:
        return await connection.run_sync(_has_pending_sync)


def _has_pending_sync(sync_connection) -> bool:
    config = _alembic_config()
    config.attributes["connection"] = sync_connection
    current = set(MigrationContext.configure(sync_connection).get_current_heads())
    heads = set(ScriptDirectory.from_config(config).get_heads())
    return current != heads


async def _configured_backup_keep(engine: AsyncEngine) -> int:
    """读取 backup_keep_count；旧库/首次启动/非法值时回退默认值。"""
    if database_path(str(engine.url)) is None:
        return BACKUP_KEEP

    def read(sync_connection) -> int:
        try:
            settings_table = table(
                "settings",
                column("key", String),
                column("value", String),
            )
            row = sync_connection.execute(
                select(settings_table.c.value).where(
                    settings_table.c.key == "backup_keep_count"
                )
            ).first()
            if row is None:
                return BACKUP_KEEP
            value = int(str(row[0]))
        except Exception:  # noqa: BLE001 - 表不存在或值损坏时使用默认值
            return BACKUP_KEEP
        return min(max(value, 1), 100)

    async with engine.connect() as connection:
        return await connection.run_sync(read)


async def migrate(engine: AsyncEngine) -> Path | None:
    """仅在存在 pending migration 时备份（SQLite）并升级。"""
    if not await _has_pending_migrations(engine):
        return None
    keep = await _configured_backup_keep(engine)
    backup = backup_sqlite_database(str(engine.url), keep=keep)
    async with engine.begin() as connection:
        await connection.run_sync(upgrade_to_head)
    logger.info(format_event("migrate.done", backup.name if backup is not None else ""))
    return backup
