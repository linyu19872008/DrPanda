"""RabbitMQ Management API 只读闸门（planning 6.3 / 6.6）：只允许 GET。"""

from __future__ import annotations

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    guard_rejected,
)


def check_rabbit(method: str, path: str) -> Decision:
    if not isinstance(method, str) or not isinstance(path, str) or not path:
        return guard_rejected("rabbit.invalid_request", "方法与路径都不能为空")
    upper = method.upper()
    if upper not in forbidden.RABBIT_ALLOWED_METHODS:
        return guard_rejected(
            "rabbit.method_not_allowed", f"RabbitMQ 只允许 GET，收到 {upper}"
        )
    if not path.startswith(forbidden.RABBIT_ALLOWED_PATH_PREFIX):
        return guard_rejected(
            "rabbit.path_not_allowed",
            f"只允许 Management API 路径 {forbidden.RABBIT_ALLOWED_PATH_PREFIX}",
        )
    return allow({"method": upper, "path": path})
