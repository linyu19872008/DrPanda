"""Elasticsearch 只读闸门（planning 6.3 / 6.6）。

只允许 GET / HEAD，以及路径以 ``_search`` / ``_count`` 结尾的 POST；
脚本、深分页、强制统计、超大 terms 聚合返回 ``DANGEROUS_OPERATION``。
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


def check_http(method: str, path: str, body: Mapping[str, Any] | None = None) -> Decision:
    """检查一次 ES 请求（方法 + 路径 + 可选请求体）。"""
    if not isinstance(method, str) or not isinstance(path, str) or not path:
        return guard_rejected("es.invalid_request", "方法与路径都不能为空")

    upper = method.upper()
    clean_path = path.split("?", 1)[0]

    if upper not in forbidden.ES_ALLOWED_METHODS:
        return guard_rejected("es.method_not_allowed", f"不允许的 HTTP 方法 {upper}")

    if any(part in forbidden.ES_FORBIDDEN_PATH_PARTS for part in clean_path.split("/")):
        return guard_rejected(
            "es.wildcard_index", "不允许 _all 或 * 作为索引，先在目标里登记允许索引"
        )

    if upper == "POST":
        if not clean_path.endswith(forbidden.ES_POST_PATH_SUFFIXES):
            return guard_rejected(
                "es.post_path_not_allowed", "POST 只允许 _search 与 _count"
            )
        if not isinstance(body, Mapping):
            return guard_rejected("es.invalid_body", "POST 请求体必须是对象")
        decision = _check_body(body)
        if not decision.allowed:
            return decision
        return allow({"method": upper, "path": clean_path, "body": dict(body)})

    return allow({"method": upper, "path": clean_path, "body": None})


def _check_body(body: Mapping[str, Any]) -> Decision:
    for key in _find_keys(body):
        if key in forbidden.ES_DANGEROUS_BODY_KEYS:
            return dangerous("es.script", f"不允许脚本相关字段 {key}")

    if body.get("track_total_hits") is True:
        return dangerous(
            "es.track_total_hits", "track_total_hits=true 会统计全量命中，开销不可控"
        )

    total = _int(body.get("from")) + _int(body.get("size"))
    if total > forbidden.ES_MAX_WINDOW:
        return dangerous(
            "es.deep_pagination", f"from + size 不能超过 {forbidden.ES_MAX_WINDOW}"
        )

    if _has_large_terms(body):
        return dangerous(
            "es.large_terms_agg",
            f"terms 聚合 size 不能超过 {forbidden.ES_MAX_TERMS_SIZE}",
        )

    return allow()


def _find_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                keys.append(key)
            keys.extend(_find_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_find_keys(item))
    return keys


def _has_large_terms(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                key == "terms"
                and isinstance(item, Mapping)
                and _int(item.get("size")) > forbidden.ES_MAX_TERMS_SIZE
            ):
                return True
            if _has_large_terms(item):
                return True
    elif isinstance(value, list):
        return any(_has_large_terms(item) for item in value)
    return False


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
