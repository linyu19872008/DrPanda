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
    default_environment_id = _default_environment_id()
    if default_environment_id is None:
        raise RuntimeError("default environment was not seeded")
    targets = sa.table(
        "targets",
        sa.column("environment_id", sa.BigInteger().with_variant(sa.Integer, "sqlite")),
    )
    op.execute(
        targets.update().values(environment_id=default_environment_id)
    )
    with op.batch_alter_table("targets") as batch:
        batch.alter_column(
            "environment_id",
            existing_type=sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            existing_nullable=True,
            nullable=False,
        )
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


def _environments_table() -> sa.TableClause:
    return sa.table(
        "environments",
        sa.column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite")),
        sa.column("key", sa.String(64)),
        sa.column("title", sa.String(64)),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _default_environment_id() -> int | None:
    environments = _environments_table()
    return op.get_bind().execute(
        sa.select(environments.c.id).where(environments.c.key == "default")
    ).scalar_one_or_none()


def _seed_default_environment() -> None:
    if _default_environment_id() is not None:
        return
    now = datetime.now(UTC)
    environments = _environments_table()
    op.get_bind().execute(
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
