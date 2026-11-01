"""Kafka 只读闸门（planning 6.3 / 6.6）。

只允许描述类管理与按分区 offset 的有限拉取；创建/删除/改配置、
加入消费组、提交 offset、生产消息一律拒绝。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    dangerous,
    guard_rejected,
)


def check_kafka(action: str, request: Mapping[str, Any] | None = None) -> Decision:
    if not isinstance(action, str) or not action:
        return guard_rejected("kafka.empty_action", "动作不能为空")
    if action in forbidden.KAFKA_DANGEROUS_ACTIONS:
        return dangerous(
            "kafka.write_or_group", f"不允许 Kafka 写操作或消费组操作：{action}"
        )
    if action not in forbidden.KAFKA_READ_ACTIONS:
        return guard_rejected("kafka.action_not_allowed", f"不允许的动作：{action}")

    request = request or {}
    if not isinstance(request, Mapping):
        return guard_rejected("kafka.invalid_request", "参数必须是对象")

    normalized: dict[str, Any] = {"action": action, "request": dict(request)}
    if action == "fetch":
        partition = _as_int(request.get("partition"))
        offset = _as_int(request.get("offset"))
        limit = _as_int(request.get("limit"))
        if partition is None or partition < 0:
            return guard_rejected("kafka.invalid_partition", "fetch 必须指定分区")
        if offset is None or offset < 0:
            return guard_rejected("kafka.invalid_offset", "fetch 必须指定非负 offset")
        if limit is None or limit <= 0:
            return guard_rejected("kafka.invalid_limit", "fetch 必须指定正整数 limit")
        normalized.update({"partition": partition, "offset": offset, "limit": limit})

    return allow(normalized)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
