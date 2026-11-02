from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from dr_panda_mcp.config import Config
from dr_panda_mcp.runtime import create_runtime
from dr_panda_mcp.store.protocol import AuditEntry


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8111,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'dr-panda.sqlite'}",
        secret_key_b64=None,
        log_level="INFO",
    )


def _copy_main(tmp_path: Path) -> Path:
    source = tmp_path / "dr-panda.sqlite"
    target = tmp_path / "main-only.sqlite"
    shutil.copy2(source, target)
    return target


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


async def test_startup_checkpoint_makes_schema_visible_in_main_file(
    tmp_path: Path,
) -> None:
    runtime = await create_runtime(
        _config(tmp_path), key_file=tmp_path / "data" / "secret.key"
    )
    try:
        tables = _tables(_copy_main(tmp_path))
    finally:
        await runtime.close()

    assert {"targets", "audit", "settings", "alembic_version"} <= tables


async def test_shutdown_checkpoint_merges_new_audit_into_main_file(
    tmp_path: Path,
) -> None:
    runtime = await create_runtime(
        _config(tmp_path), key_file=tmp_path / "data" / "secret.key"
    )
    await runtime.store.append_audit(
        AuditEntry(actor="anonymous", action="wal.checkpoint", summary="test")
    )
    await runtime.close()

    with sqlite3.connect(_copy_main(tmp_path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM audit WHERE action = 'wal.checkpoint'"
        ).fetchone()[0]
    assert count == 1
