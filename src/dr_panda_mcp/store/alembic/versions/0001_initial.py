"""初始表结构：targets / audit / settings，并写入系统配置默认值。"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

DEFAULT_SETTINGS = {
    "audit_retention_days": "90",
    "target_max_concurrency": "10",
}


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("secret_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.String(512), nullable=True),
        sa.UniqueConstraint("name", name="uq_targets_name"),
    )
    op.create_index("ix_targets_type", "targets", ["type"])

    op.create_table(
        "audit",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_name", sa.String(64), nullable=True),
        sa.Column("summary", sa.String(1024), nullable=True),
    )
    op.create_index("ix_audit_created_at", "audit", ["created_at"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    _seed_default_settings()


def _seed_default_settings() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    settings = sa.table(
        "settings",
        sa.column("key", sa.String(64)),
        sa.column("value", sa.String(64)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing = {row[0] for row in connection.execute(sa.select(settings.c.key))}
    rows = [
        {"key": key, "value": value, "updated_at": now}
        for key, value in DEFAULT_SETTINGS.items()
        if key not in existing
    ]
    if rows:
        connection.execute(settings.insert(), rows)


def downgrade() -> None:
    op.drop_index("ix_audit_created_at", table_name="audit")
    op.drop_table("audit")
    op.drop_index("ix_targets_type", table_name="targets")
    op.drop_table("targets")
    op.drop_table("settings")
