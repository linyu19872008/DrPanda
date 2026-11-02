"""Add users and configurable web session TTL.

Revision ID: 0004_users
Revises: 0003_backup_keep
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0004_users"
down_revision = "0003_backup_keep"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mcp_token_hash", sa.String(64), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_mcp_token_hash", "users", ["mcp_token_hash"], unique=True)

    setting = {
        "key": "session_ttl_minutes",
        "value": "720",
        "value_type": "int",
        "group_key": "auth",
        "group_title": "认证与会话",
        "label": "Session 有效期",
        "description": "Web 登录会话的最长有效期；修改后现有会话也按新值校验。",
        "default_value": "720",
        "min_value": 5,
        "max_value": 10080,
        "unit": "分钟",
        "effect": "立即生效",
        "editable": True,
        "requires_restart": False,
        "sort_order": 65,
        "updated_at": datetime.now(UTC),
        "updated_by": "system",
    }
    connection = op.get_bind()
    table = sa.table(
        "settings",
        *(sa.column(key, sa.String) for key in ("key", "value", "value_type", "group_key", "group_title", "label", "description", "default_value", "unit", "effect", "updated_by")),
        sa.column("min_value", sa.BigInteger),
        sa.column("max_value", sa.BigInteger),
        sa.column("editable", sa.Boolean),
        sa.column("requires_restart", sa.Boolean),
        sa.column("sort_order", sa.BigInteger),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    exists = connection.execute(
        sa.select(table.c.key).where(table.c.key == setting["key"])
    ).first()
    if exists is None:
        connection.execute(table.insert().values(**setting))


def downgrade() -> None:
    table = sa.table("settings", sa.column("key", sa.String))
    op.execute(table.delete().where(table.c.key == "session_ttl_minutes"))
    op.drop_index("ix_users_mcp_token_hash", table_name="users")
    op.drop_table("users")
