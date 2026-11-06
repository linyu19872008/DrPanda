"""Mongo 只读闸门（planning 6.3 / 6.6）。

命令白名单 + 聚合阶段白名单；JS 执行、落盘排序、强制索引、无 ``$match`` 收口
的 ``$group`` / ``$lookup`` 返回 ``DANGEROUS_OPERATION``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dr_panda_mcp.guards import forbidden
from dr_panda_mcp.guards.protocol import (
    Decision,
    allow,
    dangerous,
    guard_rejected,
)


def check_mongo_command(command: str, document: Mapping[str, Any] | None = None) -> Decision:
    """检查 Mongo 读命令及其参数文档。"""
    if not isinstance(command, str) or not command:
        return guard_rejected("mongo.empty_command", "command must not be empty")
    if command not in forbidden.MONGO_READ_COMMANDS:
        return guard_rejected(
            "mongo.command_not_allowed", f"only read commands are allowed, got {command}"
        )

    document = document or {}
    if not isinstance(document, Mapping):
        return guard_rejected("mongo.invalid_document", "document must be an object")

    for operator in _find_js_operators(document):
        return dangerous("mongo.js_expression", f"JS expressions are not allowed: {operator}")
    if document.get("allowDiskUse") is True:
        return dangerous(
            "mongo.allow_disk_use",
            "allowDiskUse=true is not allowed; it spills sorts to disk",
        )
    if "hint" in document:
        return dangerous("mongo.hint", "forcing an index hint is not allowed")

    if command == "find" and not document.get("filter"):
        return guard_rejected("mongo.find_requires_filter", "find requires a filter")
    if command == "aggregate" and "pipeline" in document:
        return check_mongo_pipeline(document["pipeline"])

    return allow({"command": command, "document": dict(document)})


def check_mongo_pipeline(pipeline: Sequence[Mapping[str, Any]]) -> Decision:
    """检查聚合管道：阶段白名单、JS 执行、$match 收口规则。"""
    if not isinstance(pipeline, Sequence) or isinstance(pipeline, (str, bytes)):
        return guard_rejected("mongo.invalid_pipeline", "pipeline must be an array")
    if not pipeline:
        return guard_rejected("mongo.empty_pipeline", "pipeline must not be empty")

    seen_match = False
    normalized: list[dict[str, Any]] = []
    for stage in pipeline:
        if not isinstance(stage, Mapping) or len(stage) != 1:
            return guard_rejected(
                "mongo.invalid_stage", "each stage must be an object with exactly one key"
            )
        name, body = next(iter(stage.items()))
        if name in forbidden.MONGO_DANGEROUS_STAGES:
            return dangerous("mongo.dangerous_stage", f"write-result stage is not allowed: {name}")
        if name not in forbidden.MONGO_PIPELINE_STAGES:
            return guard_rejected(
                "mongo.stage_not_allowed", f"aggregation stage not allowed: {name}"
            )
        for operator in _find_js_operators(body):
            return dangerous("mongo.js_expression", f"JS expressions are not allowed: {operator}")
        if name in forbidden.MONGO_MATCH_REQUIRED_STAGES and not seen_match:
            return dangerous(
                "mongo.match_required",
                f"{name} requires a preceding $match to bound the scan; "
                "otherwise it scans the whole collection",
            )
        if name == "$match":
            seen_match = True
        if name == "$lookup" and isinstance(body, Mapping):
            from_name = body.get("from")
            if isinstance(from_name, str) and from_name.lower().startswith("system."):
                return guard_rejected(
                    "mongo.system_collection",
                    f"$lookup must not reference system collection {from_name}",
                )
        normalized.append(dict(stage))

    return allow({"stages": normalized})


def _find_js_operators(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key in forbidden.MONGO_JS_OPERATORS:
                found.append(key)
            found.extend(_find_js_operators(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            found.extend(_find_js_operators(item))
    return found
