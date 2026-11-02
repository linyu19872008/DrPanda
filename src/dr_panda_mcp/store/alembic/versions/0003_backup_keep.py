"""Add configurable SQLite backup retention.

Revision ID: 0003_backup_keep
Revises: 0002_settings_metadata
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0003_backup_keep"
down_revision = "0002_settings_metadata"
branch_labels = None
depends_on = None

SETTING = {
    "key": "backup_keep_count",
    "value": "20",
    "group_key": "advanced",
    "group_title": "高级资源",
    "label": "SQLite 备份保留数量",
    "description": "仅 SQLite 且存在 pending migration 时生效；新迁移前保留最近 N 个备份。",
    "value_type": "int",
    "default_value": "20",
    "min_value": 1,
    "max_value": 20,
    "unit": "个",
    "effect": "下一次启动迁移",
    "editable": True,
    "requires_restart": False,
    "sort_order": 80,
}


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    table = sa.table(
        "settings",
        sa.column("key", sa.String),
        sa.column("value", sa.String),
        sa.column("value_type", sa.String),
        sa.column("group_key", sa.String),
        sa.column("group_title", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("default_value", sa.String),
        sa.column("min_value", sa.BigInteger),
        sa.column("max_value", sa.BigInteger),
        sa.column("unit", sa.String),
        sa.column("effect", sa.String),
        sa.column("editable", sa.Boolean),
        sa.column("requires_restart", sa.Boolean),
        sa.column("sort_order", sa.BigInteger),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("updated_by", sa.String),
    )
    exists = connection.execute(
        sa.select(table.c.key).where(table.c.key == SETTING["key"])
    ).first()
    if exists is None:
        connection.execute(table.insert().values(**SETTING, updated_at=now, updated_by="system"))


def downgrade() -> None:
    table = sa.table("settings", sa.column("key", sa.String))
    op.execute(table.delete().where(table.c.key == "backup_keep_count"))
