"""GitLab 只读闸门（planning 6.3 / 6.6）：只允许 GET。"""

from __future__ import annotations

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    guard_rejected,
)


def check_gitlab(method: str, path: str) -> Decision:
    if not isinstance(method, str) or not isinstance(path, str) or not path:
        return guard_rejected("gitlab.invalid_request", "method and path must not be empty")
    upper = method.upper()
    if upper not in forbidden.GITLAB_ALLOWED_METHODS:
        return guard_rejected("gitlab.method_not_allowed", f"GitLab only allows GET, got {upper}")
    return allow({"method": upper, "path": path})
