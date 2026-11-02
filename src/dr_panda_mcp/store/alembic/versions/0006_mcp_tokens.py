"""Add multi-token MCP credentials and invalidate legacy token.

Revision ID: 0006_mcp_tokens
Revises: 0005_mcp_token_metadata
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_mcp_tokens"
down_revision = "0005_mcp_token_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_tokens",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_mcp_tokens_token_hash"),
    )
    op.create_index("ix_mcp_tokens_user_id", "mcp_tokens", ["user_id"])

    # 按用户决定：旧单 Token 不迁移、不保留名称，直接删除旧字段，旧 Token 立即失效。
    op.drop_index("ix_users_mcp_token_hash", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mcp_token_last_used_at")
        batch.drop_column("mcp_token_created_at")
        batch.drop_column("mcp_token_prefix")
        batch.drop_column("mcp_token_hash")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mcp_token_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("mcp_token_prefix", sa.String(16), nullable=True))
        batch.add_column(sa.Column("mcp_token_created_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("mcp_token_last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_index("ix_mcp_tokens_user_id", table_name="mcp_tokens")
    op.drop_table("mcp_tokens")
