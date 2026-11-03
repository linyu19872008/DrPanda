"""用户首次登录必须修改密码。

Revision ID: 0009_user_password_gate
Revises: 0008_audit_environment
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_user_password_gate"
down_revision = "0008_audit_environment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
