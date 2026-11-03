"""审计记录所属环境。

Revision ID: 0008_audit_environment
Revises: 0007_environments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_audit_environment"
down_revision = "0007_environments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit", sa.Column("environment_key", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("audit", "environment_key")
