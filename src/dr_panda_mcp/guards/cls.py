"""CLS 只读闸门（planning 6.3 / 6.6）。

只允许检索与只读描述；搜索必须带时间窗，单次窗口不超过 24 小时。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    dangerous,
    guard_rejected,
)


def check_cls(action: str, request: Mapping[str, Any] | None = None) -> Decision:
    if not isinstance(action, str) or not action:
        return guard_rejected("cls.empty_action", "动作不能为空")
    if action in forbidden.CLS_DANGEROUS_ACTIONS:
        return dangerous("cls.write_action", f"不允许 CLS 写操作：{action}")
    if action not in forbidden.CLS_READ_ACTIONS:
        return guard_rejected("cls.action_not_allowed", f"不允许的动作：{action}")

    request = request or {}
    if not isinstance(request, Mapping):
        return guard_rejected("cls.invalid_request", "参数必须是对象")

    normalized: dict[str, Any] = {"action": action, "request": dict(request)}
    if action == "search_log":
        start = _parse_time(request.get("from"))
        end = _parse_time(request.get("to"))
        if start is None or end is None:
            return guard_rejected(
                "cls.time_window_required", "日志检索必须带 from / to 时间窗"
            )
        if end < start:
            return guard_rejected("cls.invalid_window", "to 不能早于 from")
        if end - start > forbidden.CLS_MAX_WINDOW:
            return dangerous(
                "cls.window_too_large",
                f"单次时间窗不能超过 {int(forbidden.CLS_MAX_WINDOW.total_seconds() // 3600)} 小时",
            )
        normalized.update({"from": start, "to": end})

    return allow(normalized)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None
