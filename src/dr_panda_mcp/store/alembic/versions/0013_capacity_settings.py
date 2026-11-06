"""资源类系统配置：全局并发、连接器空闲回收、审计清理批量与时限。

Revision ID: 0013_capacity_settings
Revises: 0012_security_settings
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0013_capacity_settings"
down_revision = "0012_security_settings"
branch_labels = None
depends_on = None

SETTINGS = [
    {
        "key": "global_max_concurrent_calls",
        "value": "0",
        "group_key": "runtime",
        "group_title": "并发与审计",
        "label": "全局并发上限",
        "description": "整个进程同时进行的工具调用上限；0 表示不限制。达到上限的调用排队等待。",
        "value_type": "int",
        "default_value": "0",
        "min_value": 0,
        "max_value": 200,
        "unit": "个",
        "effect": "下一次取槽",
        "editable": True,
        "requires_restart": False,
        "sort_order": 140,
    },
    {
        "key": "audit_cleanup_batch_size",
        "value": "1000",
        "group_key": "runtime",
        "group_title": "并发与审计",
        "label": "审计清理批量",
        "description": "每批删除的审计条数；越大清理越快，但单次锁表时间更长。",
        "value_type": "int",
        "default_value": "1000",
        "min_value": 100,
        "max_value": 5000,
        "unit": "条",
        "effect": "下一轮清理",
        "editable": True,
        "requires_restart": False,
        "sort_order": 150,
    },
    {
        "key": "audit_cleanup_max_seconds",
        "value": "300",
        "group_key": "runtime",
        "group_title": "并发与审计",
        "label": "审计清理时限",
        "description": "单轮清理最多运行的时间；达到时限后剩余记录留到下一轮。",
        "value_type": "int",
        "default_value": "300",
        "min_value": 10,
        "max_value": 3600,
        "unit": "秒",
        "effect": "下一轮清理",
        "editable": True,
        "requires_restart": False,
        "sort_order": 160,
    },
    {
        "key": "catalog_idle_seconds",
        "value": "0",
        "group_key": "advanced",
        "group_title": "高级资源",
        "label": "连接器空闲回收",
        "description": "池中连接超过该时长未使用则关闭；0 表示不回收。修改后在下一次取客户端时按新值清理。",
        "value_type": "int",
        "default_value": "0",
        "min_value": 0,
        "max_value": 3600,
        "unit": "秒",
        "effect": "下一次取客户端",
        "editable": True,
        "requires_restart": False,
        "sort_order": 170,
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


def downgrade() -> None:
    table = sa.table("settings", sa.column("key", sa.String))
    op.execute(
        table.delete().where(
            table.c.key.in_([setting["key"] for setting in SETTINGS])
        )
    )
