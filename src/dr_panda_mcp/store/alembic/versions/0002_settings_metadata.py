"""settings 元数据、完整默认行与结构化历史。

Revision ID: 0002_settings_metadata
Revises: 0001_initial
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0002_settings_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

# 迁移内固定定义，避免未来修改运行时代码改变历史迁移行为。
SETTINGS = [
    {
        "key": "default_target_timeout_s",
        "value": "15",
        "group_key": "target_defaults",
        "group_title": "新建目标默认值",
        "label": "默认超时",
        "description": "新建目标表单的默认 timeout_s；既有目标仍使用各自配置。",
        "value_type": "int",
        "default_value": "15",
        "min_value": 1,
        "max_value": 120,
        "unit": "秒",
        "effect": "仅新建目标",
        "editable": True,
        "requires_restart": False,
        "sort_order": 10,
    },
    {
        "key": "default_target_max_rows",
        "value": "100",
        "group_key": "target_defaults",
        "group_title": "新建目标默认值",
        "label": "默认行数上限",
        "description": "新建目标表单的默认 max_rows；既有目标仍使用各自配置。",
        "value_type": "int",
        "default_value": "100",
        "min_value": 1,
        "max_value": 1000,
        "unit": "行",
        "effect": "仅新建目标",
        "editable": True,
        "requires_restart": False,
        "sort_order": 20,
    },
    {
        "key": "default_target_max_bytes",
        "value": "102400",
        "group_key": "target_defaults",
        "group_title": "新建目标默认值",
        "label": "默认字节上限",
        "description": "新建目标表单的默认 max_bytes；既有目标仍使用各自配置。",
        "value_type": "int",
        "default_value": "102400",
        "min_value": 4096,
        "max_value": 1048576,
        "unit": "字节",
        "effect": "仅新建目标",
        "editable": True,
        "requires_restart": False,
        "sort_order": 30,
    },
    {
        "key": "target_max_concurrency",
        "value": "10",
        "group_key": "runtime",
        "group_title": "并发与审计",
        "label": "每 target 并发上限",
        "description": "同一个目标同时进行的工具调用上限，超出会排队。",
        "value_type": "int",
        "default_value": "10",
        "min_value": 1,
        "max_value": 50,
        "unit": "个",
        "effect": "立即生效",
        "editable": True,
        "requires_restart": False,
        "sort_order": 40,
    },
    {
        "key": "audit_retention_days",
        "value": "90",
        "group_key": "runtime",
        "group_title": "并发与审计",
        "label": "审计保留天数",
        "description": "超过该天数的审计记录会被定时清理；清理只记日志。",
        "value_type": "int",
        "default_value": "90",
        "min_value": 1,
        "max_value": 3650,
        "unit": "天",
        "effect": "下一轮清理",
        "editable": True,
        "requires_restart": False,
        "sort_order": 50,
    },
    {
        "key": "audit_cleanup_interval_minutes",
        "value": "60",
        "group_key": "runtime",
        "group_title": "并发与审计",
        "label": "审计清理间隔",
        "description": "每轮清理后按该间隔休眠；修改后下一轮开始使用新值。",
        "value_type": "int",
        "default_value": "60",
        "min_value": 5,
        "max_value": 1440,
        "unit": "分钟",
        "effect": "下一轮清理",
        "editable": True,
        "requires_restart": False,
        "sort_order": 60,
    },
    {
        "key": "catalog_max_clients",
        "value": "32",
        "group_key": "advanced",
        "group_title": "高级资源",
        "label": "连接器缓存上限",
        "description": "进程内缓存的连接器客户端数量；修改后在下一次取客户端时按新上限淘汰。",
        "value_type": "int",
        "default_value": "32",
        "min_value": 4,
        "max_value": 128,
        "unit": "个",
        "effect": "下一次工具调用",
        "editable": True,
        "requires_restart": False,
        "sort_order": 70,
    },
]


def upgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.add_column(sa.Column("value_type", sa.String(16), nullable=False, server_default="int"))
        batch.add_column(sa.Column("group_key", sa.String(64), nullable=False, server_default="runtime"))
        batch.add_column(sa.Column("group_title", sa.String(128), nullable=False, server_default=""))
        batch.add_column(sa.Column("label", sa.String(128), nullable=False, server_default=""))
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("default_value", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("min_value", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("max_value", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("unit", sa.String(16), nullable=False, server_default=""))
        batch.add_column(sa.Column("effect", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("editable", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("requires_restart", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("sort_order", sa.BigInteger(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("updated_by", sa.String(64), nullable=False, server_default="system"))

    op.create_table(
        "settings_history",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("old_value", sa.String(64), nullable=True),
        sa.Column("new_value", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_settings_history_key", "settings_history", ["key"])
    op.create_index("ix_settings_history_changed_at", "settings_history", ["changed_at"])

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
    existing = {
        row[0] for row in connection.execute(sa.text("SELECT key FROM settings"))
    }
    for spec in SETTINGS:
        if spec["key"] in existing:
            connection.execute(
                table.update()
                .where(table.c.key == spec["key"])
                .values(**{key: value for key, value in spec.items() if key != "value"})
            )
        else:
            connection.execute(
                table.insert().values(**spec, updated_at=now, updated_by="system")
            )


def downgrade() -> None:
    op.drop_index("ix_settings_history_changed_at", table_name="settings_history")
    op.drop_index("ix_settings_history_key", table_name="settings_history")
    op.drop_table("settings_history")
    with op.batch_alter_table("settings") as batch:
        for column in [
            "updated_by",
            "sort_order",
            "requires_restart",
            "editable",
            "effect",
            "unit",
            "max_value",
            "min_value",
            "default_value",
            "description",
            "label",
            "group_title",
            "group_key",
            "value_type",
        ]:
            batch.drop_column(column)
