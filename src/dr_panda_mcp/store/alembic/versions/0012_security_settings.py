"""安全类系统配置：登录失败保护与 MCP Token 限制。

Revision ID: 0012_security_settings
Revises: 0011_audit_error_detail

新增 login_max_attempts、login_lockout_minutes、mcp_token_max_per_user、
mcp_token_ttl_days；同时把 backup_keep_count 的上限从 20 放宽到 100。
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0012_security_settings"
down_revision = "0011_audit_error_detail"
branch_labels = None
depends_on = None

SETTINGS = [
    {
        "key": "login_max_attempts",
        "value": "5",
        "group_key": "auth",
        "group_title": "认证与会话",
        "label": "登录失败次数上限",
        "description": "同一来源 IP 在锁定时长内允许的登录失败次数；达到后暂时拒绝登录。按来源 IP 计数、进程内保存，重启清零。",
        "value_type": "int",
        "default_value": "5",
        "min_value": 1,
        "max_value": 50,
        "unit": "次",
        "effect": "下一次登录校验",
        "editable": True,
        "requires_restart": False,
        "sort_order": 100,
    },
    {
        "key": "login_lockout_minutes",
        "value": "5",
        "group_key": "auth",
        "group_title": "认证与会话",
        "label": "登录锁定时长",
        "description": "达到失败次数后拒绝该来源登录的时长；到期自动解除。",
        "value_type": "int",
        "default_value": "5",
        "min_value": 1,
        "max_value": 1440,
        "unit": "分钟",
        "effect": "下一次登录校验",
        "editable": True,
        "requires_restart": False,
        "sort_order": 110,
    },
    {
        "key": "mcp_token_max_per_user",
        "value": "5",
        "group_key": "auth",
        "group_title": "认证与会话",
        "label": "每人 Token 上限",
        "description": "每个账号最多保留的 MCP Token 数量；达到上限后需先删除旧 Token。",
        "value_type": "int",
        "default_value": "5",
        "min_value": 1,
        "max_value": 50,
        "unit": "个",
        "effect": "下一次生成 Token",
        "editable": True,
        "requires_restart": False,
        "sort_order": 120,
    },
    {
        "key": "mcp_token_ttl_days",
        "value": "0",
        "group_key": "auth",
        "group_title": "认证与会话",
        "label": "Token 有效期",
        "description": "Token 从创建起算的有效天数；0 表示不过期，过期后 MCP 调用返回未认证。",
        "value_type": "int",
        "default_value": "0",
        "min_value": 0,
        "max_value": 3650,
        "unit": "天",
        "effect": "下一次 MCP 调用",
        "editable": True,
        "requires_restart": False,
        "sort_order": 130,
    },
]


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
    for setting in SETTINGS:
        exists = connection.execute(
            sa.select(table.c.key).where(table.c.key == setting["key"])
        ).first()
        if exists is None:
            connection.execute(
                table.insert().values(**setting, updated_at=now, updated_by="system")
            )
    connection.execute(
        table.update()
        .where(table.c.key == "backup_keep_count")
        .values(
            max_value=100,
            description="仅 SQLite 且存在 pending migration 时生效；新迁移前保留最近 N 个备份（1–100）。",
            updated_at=now,
            updated_by="system",
        )
    )


def downgrade() -> None:
    table = sa.table(
        "settings",
        sa.column("key", sa.String),
        sa.column("max_value", sa.BigInteger),
        sa.column("description", sa.Text),
    )
    op.execute(
        table.delete().where(
            table.c.key.in_([setting["key"] for setting in SETTINGS])
        )
    )
    connection = op.get_bind()
    connection.execute(
        table.update()
        .where(table.c.key == "backup_keep_count")
        .values(
            max_value=20,
            description="仅 SQLite 且存在 pending migration 时生效；新迁移前保留最近 N 个备份。",
        )
    )
