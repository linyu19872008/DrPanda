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
        return guard_rejected("es.invalid_request", "method and path must not be empty")

    upper = method.upper()
    clean_path = path.split("?", 1)[0]

    if upper not in forbidden.ES_ALLOWED_METHODS:
        return guard_rejected("es.method_not_allowed", f"HTTP method not allowed: {upper}")

    if any(part in forbidden.ES_FORBIDDEN_PATH_PARTS for part in clean_path.split("/")):
        return guard_rejected(
            "es.wildcard_index",
            "_all or * is not allowed as an index; register allowed indices "
            "on the target first",
        )

    if upper == "POST":
        if not clean_path.endswith(forbidden.ES_POST_PATH_SUFFIXES):
            return guard_rejected(
                "es.post_path_not_allowed", "POST is only allowed for _search and _count"
            )
        if not isinstance(body, Mapping):
            return guard_rejected("es.invalid_body", "POST body must be an object")
        decision = _check_body(body)
        if not decision.allowed:
            return decision
        return allow({"method": upper, "path": clean_path, "body": dict(body)})

    return allow({"method": upper, "path": clean_path, "body": None})


def _check_body(body: Mapping[str, Any]) -> Decision:
    for key in _find_keys(body):
        if key in forbidden.ES_DANGEROUS_BODY_KEYS:
            return dangerous("es.script", f"script-related field not allowed: {key}")

    if body.get("track_total_hits") is True:
        return dangerous(
            "es.track_total_hits",
            "track_total_hits=true counts all hits and has unbounded cost",
        )

    total = _int(body.get("from")) + _int(body.get("size"))
    if total > forbidden.ES_MAX_WINDOW:
        return dangerous(
            "es.deep_pagination", f"from + size must not exceed {forbidden.ES_MAX_WINDOW}"
        )

    decision = _check_aggs(body)
    if not decision.allowed:
        return decision
    if _has_large_terms(body):
        return dangerous(
            "es.large_terms_agg",
            f"terms aggregation size must not exceed {forbidden.ES_MAX_TERMS_SIZE}",
        )

    return allow()


def _check_aggs(body: Mapping[str, Any]) -> Decision:
    aggs = body.get("aggs", body.get("aggregations"))
    if aggs is None:
        return allow()
    if not isinstance(aggs, Mapping):
        return guard_rejected("es.invalid_aggs", "aggs must be an object")
    return _walk_aggs(aggs)


def _walk_aggs(aggs: Mapping[str, Any]) -> Decision:
    for spec in aggs.values():
        if not isinstance(spec, Mapping):
            return guard_rejected("es.invalid_agg", "each aggregation definition must be an object")
        for key in spec:
            if key in {"aggs", "aggregations", "meta"}:
                continue
            if key not in forbidden.ES_ALLOWED_AGG_TYPES:
                return dangerous(
                    "es.agg_type_not_allowed",
                    f"only bounded terms aggregations are allowed, got {key}; "
                    "use a detail query or split the range",
                )
            terms = spec[key]
            if not isinstance(terms, Mapping):
                return guard_rejected("es.invalid_terms_agg", "terms aggregation must be an object")
            if _int(terms.get("size")) > forbidden.ES_MAX_TERMS_SIZE:
                return dangerous(
                    "es.large_terms_agg",
                    f"terms aggregation size must not exceed {forbidden.ES_MAX_TERMS_SIZE}",
                )
        nested = spec.get("aggs", spec.get("aggregations"))
        if nested is not None:
            if not isinstance(nested, Mapping):
                return guard_rejected("es.invalid_aggs", "nested aggs must be an object")
            decision = _walk_aggs(nested)
            if not decision.allowed:
                return decision
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
