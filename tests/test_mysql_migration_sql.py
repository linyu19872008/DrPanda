"""Regression checks for MySQL reserved words in Alembic migrations."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "src/dr_panda_mcp/store/alembic/versions/0007_environments.py"


def _environment_table() -> sa.TableClause:
    module = import_module("dr_panda_mcp.store.alembic.versions.0007_environments")
    return module._environments_table()


def test_environment_query_quotes_reserved_key_for_mysql() -> None:
    environments = _environment_table()
    statement = sa.select(environments.c.id).where(environments.c.key == "default")
    compiled = str(statement.compile(dialect=mysql.dialect()))

    assert "`key`" in compiled
    assert "WHERE environments.key" not in compiled


def test_environment_insert_quotes_reserved_key_for_mysql() -> None:
    environments = _environment_table()
    statement = environments.insert().values(
        key="default", title="Default", enabled=True
    )
    compiled = str(statement.compile(dialect=mysql.dialect()))

    assert "`key`" in compiled


def test_migration_no_longer_contains_raw_key_predicate() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "WHERE key = 'default'" not in source
    assert "WHERE key =" not in source
