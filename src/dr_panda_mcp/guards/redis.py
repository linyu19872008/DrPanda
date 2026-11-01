"""Redis 只读闸门（planning 6.3 / 6.6）。

命令白名单 + 高开销规则：无界范围、过大的 SCAN COUNT、管理命令一律拒绝。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    dangerous,
    guard_rejected,
)


def check_redis(command: str, args: Sequence[Any] = ()) -> Decision:
    """检查一条 Redis 命令。"""
    if not isinstance(command, str) or not command:
        return guard_rejected("redis.empty_command", "命令不能为空")
    upper = command.upper()
    if upper not in forbidden.REDIS_READ_COMMANDS:
        return guard_rejected(
            "redis.command_not_allowed", f"只允许只读命令，收到 {upper}"
        )

    values = list(args)

    if upper == "SLOWLOG":
        sub = str(values[0]).upper() if values else ""
        if sub != "GET":
            return guard_rejected("redis.slowlog_subcommand", "SLOWLOG 只允许 GET")
        return allow({"command": upper, "args": values})

    if upper == "MEMORY":
        sub = str(values[0]).upper() if values else ""
        if sub != "USAGE":
            return guard_rejected("redis.memory_subcommand", "MEMORY 只允许 USAGE")
        return allow({"command": upper, "args": values})

    if upper in {"SCAN", "HSCAN"}:
        present, count = _count_argument(values)
        if not present:
            return allow({"command": upper, "args": values, "count": 10})
        if count is None:
            return guard_rejected("redis.invalid_count", "COUNT 必须是整数")
        if count > forbidden.REDIS_MAX_SCAN_COUNT:
            return dangerous(
                "redis.scan_count_too_large",
                f"SCAN COUNT 不能超过 {forbidden.REDIS_MAX_SCAN_COUNT}",
            )
        return allow({"command": upper, "args": values, "count": count})

    if upper in forbidden.REDIS_UNBOUNDED_RANGE_COMMANDS:
        decision = _check_range(upper, values)
        if not decision.allowed:
            return decision
        return decision

    if upper in forbidden.REDIS_NEEDS_SIZE_PROBE:
        return allow({"command": upper, "args": values, "probe": "SCARD"})

    return allow({"command": upper, "args": values})


def _check_range(command: str, values: list[Any]) -> Decision:
    if len(values) < 3:
        return guard_rejected(
            "redis.invalid_range", f"{command} 需要 key 与起止下标"
        )
    start, stop = _to_int(values[1]), _to_int(values[2])
    if start is None or stop is None:
        return guard_rejected("redis.invalid_range", "起止下标必须是整数")
    if stop < 0:
        return dangerous(
            "redis.unbounded_range",
            f"{command} 的 end 不能是 {stop}（到集合末尾即无界）",
        )
    if stop < start:
        return guard_rejected("redis.invalid_range", "end 不能小于 start")
    return allow({"command": command, "args": values, "span": stop - start + 1})


def _count_argument(values: Sequence[Any]) -> tuple[bool, int | None]:
    for index, value in enumerate(values):
        if str(value).upper() == "COUNT" and index + 1 < len(values):
            return True, _to_int(values[index + 1])
    return False, None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
