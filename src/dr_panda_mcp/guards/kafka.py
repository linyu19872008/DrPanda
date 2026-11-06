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
        return guard_rejected("kafka.empty_action", "action must not be empty")
    if action in forbidden.KAFKA_DANGEROUS_ACTIONS:
        return dangerous(
            "kafka.write_or_group", f"Kafka write or consumer-group operations are not allowed: {action}"
        )
    if action not in forbidden.KAFKA_READ_ACTIONS:
        return guard_rejected("kafka.action_not_allowed", f"action not allowed: {action}")

    request = request or {}
    if not isinstance(request, Mapping):
        return guard_rejected("kafka.invalid_request", "request must be an object")

    normalized: dict[str, Any] = {"action": action, "request": dict(request)}
    if action == "fetch":
        partition = _as_int(request.get("partition"))
        offset = _as_int(request.get("offset"))
        limit = _as_int(request.get("limit"))
        if partition is None or partition < 0:
            return guard_rejected("kafka.invalid_partition", "fetch requires a partition")
        if offset is None or offset < 0:
            return guard_rejected("kafka.invalid_offset", "fetch requires a non-negative offset")
        if limit is None or limit <= 0:
            return guard_rejected("kafka.invalid_limit", "fetch requires a positive integer limit")
        normalized.update({"partition": partition, "offset": offset, "limit": limit})

    return allow(normalized)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
