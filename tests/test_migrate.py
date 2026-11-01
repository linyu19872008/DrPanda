from __future__ import annotations

import sqlite3
from pathlib import Path

from dr_panda_mcp.store.migrate import BACKUP_KEEP, backup_sqlite_database, migrate
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

    assert {"targets", "audit", "settings", "alembic_version"} <= tables
    assert settings_rows == {
        "audit_retention_days": "90",
        "target_max_concurrency": "10",
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
