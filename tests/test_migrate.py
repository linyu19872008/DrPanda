from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from alembic import command

from dr_panda_mcp.store.migrate import (
    BACKUP_KEEP,
    _alembic_config,
    backup_sqlite_database,
    migrate,
)
from dr_panda_mcp.store.url import create_engine


def _url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'dr-panda.sqlite'}"


async def test_migrate_creates_tables_and_defaults(tmp_path: Path) -> None:
    engine = create_engine(_url(tmp_path))
    try:
        await migrate(engine)
    finally:
        await engine.dispose()

    with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        settings_rows = dict(
            connection.execute("SELECT key, value FROM settings")
        )

    assert {"targets", "audit", "settings", "settings_history", "alembic_version"} <= tables
    assert settings_rows == {
        "audit_retention_days": "90",
        "target_max_concurrency": "10",
        "default_target_timeout_s": "15",
        "default_target_max_rows": "100",
        "default_target_max_bytes": "102400",
        "audit_cleanup_interval_minutes": "60",
        "catalog_max_clients": "32",
        "backup_keep_count": "20",
        "session_ttl_minutes": "720",
    }


async def test_migrate_is_idempotent_and_keeps_user_settings(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    try:
        await migrate(engine)
        with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
            connection.execute(
                "UPDATE settings SET value = '30' WHERE key = 'audit_retention_days'"
            )
        await migrate(engine)
        await migrate(engine)
    finally:
        await engine.dispose()

    with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
        values = dict(connection.execute("SELECT key, value FROM settings"))
    assert values["audit_retention_days"] == "30"


async def test_backup_created_and_pruned(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    try:
        await migrate(engine)
    finally:
        await engine.dispose()

    for _ in range(BACKUP_KEEP + 3):
        created = backup_sqlite_database(url)
        assert created is not None and created.exists()

    backups = list((tmp_path / "backup").glob("*.sqlite"))
    assert 0 < len(backups) <= BACKUP_KEEP


def test_backup_skipped_for_memory_database() -> None:
    assert backup_sqlite_database("sqlite+aiosqlite:///:memory:") is None


async def test_backup_includes_wal_transactions(tmp_path: Path) -> None:
    database = tmp_path / "dr-panda.sqlite"
    writer = sqlite3.connect(database)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO t (value) VALUES ('in-wal')")
        writer.commit()

        backup = backup_sqlite_database(_url(tmp_path))
        assert backup is not None
        with sqlite3.connect(backup) as reader:
            assert reader.execute("SELECT value FROM t").fetchone() == ("in-wal",)
    finally:
        writer.close()


async def test_settings_metadata_is_seeded(tmp_path: Path) -> None:
    engine = create_engine(_url(tmp_path))
    try:
        await migrate(engine)
    finally:
        await engine.dispose()

    with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
        rows = connection.execute(
            "SELECT key, value, group_key, group_title, label, default_value, "
            "min_value, max_value, unit, effect, editable, requires_restart, updated_by "
            "FROM settings ORDER BY sort_order"
        ).fetchall()

    assert [row[0] for row in rows] == [
        "default_target_timeout_s",
        "default_target_max_rows",
        "default_target_max_bytes",
        "target_max_concurrency",
        "audit_retention_days",
        "audit_cleanup_interval_minutes",
        "session_ttl_minutes",
        "catalog_max_clients",
        "backup_keep_count",
    ]
    catalog = next(row for row in rows if row[0] == "backup_keep_count")
    assert catalog[2:] == (
        "advanced",
        "高级资源",
        "SQLite 备份保留数量",
        "20",
        1,
        20,
        "个",
        "下一次启动迁移",
        1,
        0,
        "system",
    )


async def test_settings_migration_preserves_existing_values(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    try:
        def upgrade_to_initial(sync_connection) -> None:
            config = _alembic_config()
            config.attributes["connection"] = sync_connection
            command.upgrade(config, "0001_initial")

        async with engine.begin() as connection:
            await connection.run_sync(upgrade_to_initial)

        with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
            connection.execute(
                "UPDATE settings SET value = '30' WHERE key = 'audit_retention_days'"
            )

        await migrate(engine)
    finally:
        await engine.dispose()

    with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
        row = connection.execute(
            "SELECT value, group_key, label FROM settings WHERE key = 'audit_retention_days'"
        ).fetchone()
        count = connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0]

    assert row == ("30", "runtime", "审计保留天数")
    assert count == 9


async def test_no_backup_when_no_pending_migration(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    try:
        # 首次升级本身是 pending，允许产生迁移前备份；这里只验证升级后再次启动不再新增。
        await migrate(engine)
        backup_dir = tmp_path / "backup"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        await migrate(engine)
        second = list(backup_dir.glob("*.sqlite")) if backup_dir.exists() else []
    finally:
        await engine.dispose()

    assert second == []


async def test_pending_migration_uses_configured_backup_keep(tmp_path: Path) -> None:
    url = _url(tmp_path)
    engine = create_engine(url)
    try:
        await migrate(engine)
        with sqlite3.connect(tmp_path / "dr-panda.sqlite") as connection:
            connection.execute(
                "UPDATE settings SET value = '3' WHERE key = 'backup_keep_count'"
            )
            for _ in range(5):
                backup_sqlite_database(url, keep=20)
            connection.execute("DROP TABLE mcp_tokens")
            connection.execute("DROP TABLE users")
            connection.execute(
                "UPDATE alembic_version SET version_num = '0003_backup_keep'"
            )

        created = await migrate(engine)
    finally:
        await engine.dispose()

    backups = sorted((tmp_path / "backup").glob("*.sqlite"))
    assert created is not None
    assert len(backups) == 3
