"""Add MCP token display metadata.

Revision ID: 0005_mcp_token_metadata
Revises: 0004_users
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_mcp_token_metadata"
down_revision = "0004_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mcp_token_prefix", sa.String(16), nullable=True))
        batch.add_column(sa.Column("mcp_token_created_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("mcp_token_last_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mcp_token_last_used_at")
        batch.drop_column("mcp_token_created_at")
        batch.drop_column("mcp_token_prefix")
