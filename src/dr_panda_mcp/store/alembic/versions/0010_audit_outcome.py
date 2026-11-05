"""审计结果结构化：新增 audit.outcome 并按 summary 回填。

Revision ID: 0010_audit_outcome
Revises: 0009_user_password_gate

只有 tool.call 与 target.test 有成败语义：
- tool.call 的 summary 以 ``error=<code>`` 结尾（成功为 ``error=-``）；
- target.test 的 summary 是 ``ok`` 或 ``failed: <原因>``。
迁移一次性回填历史行，之后由写入路径直接落 outcome。
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0010_audit_outcome"
down_revision = "0009_user_password_gate"
branch_labels = None
depends_on = None

_TOOL_ERROR = re.compile(r"(?:^|\s)error=(?P<value>\S+)")
_BATCH = 500


def upgrade() -> None:
    op.add_column("audit", sa.Column("outcome", sa.String(8), nullable=True))
    _backfill_outcomes()


def downgrade() -> None:
    op.drop_column("audit", "outcome")


def _backfill_outcomes() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, action, summary FROM audit")).fetchall()
    updates: list[dict[str, object]] = []
    for row_id, action, summary in rows:
        outcome = _outcome_of(action, summary)
        if outcome is not None:
            updates.append({"row_id": row_id, "outcome": outcome})
    statement = sa.text("UPDATE audit SET outcome = :outcome WHERE id = :row_id")
    for start in range(0, len(updates), _BATCH):
        bind.execute(statement, updates[start : start + _BATCH])


def _outcome_of(action: str | None, summary: str | None) -> str | None:
    text = (summary or "").strip()
    if action == "tool.call":
        match = _TOOL_ERROR.search(text)
        if match is None:
            return None
        return "ok" if match.group("value") == "-" else "failed"
    if action == "target.test":
        if text == "ok":
            return "ok"
        if text.startswith("failed"):
            return "failed"
    return None
