"""审计失败详情：新增 audit.error_detail。

Revision ID: 0011_audit_error_detail
Revises: 0010_audit_outcome

只有 tool.call 失败时写入：脱敏、截断（512）后的错误消息；旧行为 NULL，
渲染时按 NULL 处理，无需回填。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_audit_error_detail"
down_revision = "0010_audit_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit", sa.Column("error_detail", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("audit", "error_detail")
