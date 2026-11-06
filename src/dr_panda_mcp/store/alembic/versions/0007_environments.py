"""环境：目标按环境隔离，名称在环境内唯一。

Revision ID: 0007_environments
Revises: 0006_mcp_tokens
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0007_environments"
down_revision = "0006_mcp_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_environments_key"),
    )
    _seed_default_environment()
    op.add_column(
        "targets",
        sa.Column(
            "environment_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE targets SET environment_id = "
            "(SELECT id FROM environments WHERE key = 'default')"
        )
    )
    with op.batch_alter_table("targets") as batch:
        batch.alter_column("environment_id", nullable=False)
        batch.create_foreign_key(
            "fk_targets_environment_id",
            "environments",
            ["environment_id"],
            ["id"],
        )
        batch.drop_constraint("uq_targets_name", type_="unique")
        batch.create_unique_constraint(
            "uq_targets_environment_name", ["environment_id", "name"]
        )
    op.create_index("ix_targets_environment_id", "targets", ["environment_id"])


def _seed_default_environment() -> None:
    connection = op.get_bind()
    existing = connection.execute(
        sa.text("SELECT id FROM environments WHERE key = 'default'")
    ).first()
    if existing:
        return
    now = datetime.now(UTC)
    environments = sa.table(
        "environments",
        sa.column("key", sa.String(64)),
        sa.column("title", sa.String(64)),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection.execute(
        environments.insert().values(
            key="default",
            title="Default",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )


def downgrade() -> None:
    op.drop_index("ix_targets_environment_id", table_name="targets")
    with op.batch_alter_table("targets") as batch:
        batch.drop_constraint("uq_targets_environment_name", type_="unique")
        batch.drop_constraint("fk_targets_environment_id", type_="foreignkey")
        batch.create_unique_constraint("uq_targets_name", ["name"])
        batch.drop_column("environment_id")
    op.drop_table("environments")
