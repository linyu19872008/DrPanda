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
        return guard_rejected("rabbit.invalid_request", "method and path must not be empty")
    upper = method.upper()
    if upper not in forbidden.RABBIT_ALLOWED_METHODS:
        return guard_rejected(
            "rabbit.method_not_allowed", f"RabbitMQ only allows GET, got {upper}"
        )
    if not path.startswith(forbidden.RABBIT_ALLOWED_PATH_PREFIX):
        return guard_rejected(
            "rabbit.path_not_allowed",
            f"only Management API paths under "
            f"{forbidden.RABBIT_ALLOWED_PATH_PREFIX} are allowed",
        )
    return allow({"method": upper, "path": path})
