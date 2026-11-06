"""闸门公共类型：结论、拒绝构造与强制执行（planning 6.2 / 6.6）。

闸门函数是纯函数：不联网、不读数据库、可单测。返回 ``Decision``；
调用方用 :func:`require` 在建立连接之前强制执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dr_panda_mcp import errors


@dataclass(frozen=True)
class Decision:
    """一次检查的结论。``error_code`` 取 ``GUARD_REJECTED`` 或 ``DANGEROUS_OPERATION``。"""

    allowed: bool
    error_code: str | None = None
    reason: str | None = None
    detail: str | None = None
    normalized: Any = None


def allow(normalized: Any = None) -> Decision:
    return Decision(True, normalized=normalized)


def guard_rejected(reason: str, detail: str) -> Decision:
    """白名单拒绝（写操作、无法解析、超出允许形态）。"""
    return Decision(
        False, error_code=errors.GUARD_REJECTED, reason=reason, detail=detail
    )


def dangerous(reason: str, detail: str) -> Decision:
    """危险或高开销操作拒绝（默认拒绝，无配置可放开）。"""
    return Decision(
        False, error_code=errors.DANGEROUS_OPERATION, reason=reason, detail=detail
    )


def require(decision: Decision) -> Any:
    """放行则返回规范化结果；拒绝则抛 ``GuardRejected``（带错误码）。"""
    if not decision.allowed:
        message = decision.detail or decision.reason or "request rejected"
        raise errors.GuardRejected(message, code=decision.error_code)
    return decision.normalized
