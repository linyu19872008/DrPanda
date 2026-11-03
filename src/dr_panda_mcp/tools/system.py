"""`systems_status`：先列出环境，再列出某个环境里的目标。"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.tools.base import EnvironmentParam, code_for


def register_systems_status(server: FastMCP, runtime: Runtime) -> None:
    @server.tool(annotations={"readOnlyHint": True})
    async def systems_status(environment: EnvironmentParam = "") -> dict[str, Any]:
        """列出环境，或列出某个环境里的目标与最近连通性。

        不传 environment 时只返回环境（key、展示名、目标数）。
        传入后只返回该环境的目标。同一种类型有多台时，后续调用必须点名 target。
        """
        key = environment.strip()
        try:
            with base.Stopwatch() as watch:
                payload = (
                    await _environments(runtime)
                    if not key
                    else await _targets(runtime, key)
                )
                payload["elapsed_ms"] = watch.elapsed_ms
                return payload
        except errors.DrPandaError as exc:
            raise ToolError(f"{code_for(exc)}: {exc}") from exc


async def _environments(runtime: Runtime) -> dict[str, Any]:
    environments = await runtime.store.list_environments()
    rows = [
        {
            "key": item.key,
            "title": item.title,
            "enabled": item.enabled,
            "targets": item.target_count,
            "enabled_targets": item.enabled_target_count,
        }
        for item in environments
    ]
    notes = [
        "这是环境列表，不是目标列表。要看某个环境里的目标，请传入 environment=它的 key。",
        "title 是展示名，key 才是工具参数。登记了多个环境时，后续调用必须传 environment。",
        "同一个环境里同一种类型可能有多台，调用时必须传 target，不会自动挑选。",
    ]
    if len(environments) == 1:
        notes.append("当前只登记了一个环境，工具调用可以省略 environment。")
    return _envelope(
        summary="environments",
        rows=rows,
        stats={
            "environments": len(rows),
            "enabled": sum(1 for row in rows if row["enabled"]),
            "targets": sum(int(row["targets"]) for row in rows),
            "enabled_targets": sum(int(row["enabled_targets"]) for row in rows),
        },
        notes=notes,
    )


async def _targets(runtime: Runtime, key: str) -> dict[str, Any]:
    environments = await runtime.store.list_environments()
    match = next((item for item in environments if item.key == key), None)
    if match is None:
        choices = "、".join(f"{item.key}（{item.title}）" for item in environments)
        suffix = f"。可选：{choices}" if choices else ""
        raise errors.EnvironmentNotFound(f"环境 {key} 未登记{suffix}")
    targets = await runtime.store.list_by_environment(key)
    rows = [
        {
            "name": target.name,
            "type": target.type,
            "enabled": target.enabled,
            "last_test_at": _iso(target.last_test_at),
            "last_test_ok": target.last_test_ok,
            "last_test_error": target.last_test_error,
        }
        for target in targets
    ]
    notes = [
        f"环境 {match.key}（{match.title}）。",
        "同一种类型有多台时必须传入对应的 target，不会自动挑选。",
    ]
    if not match.enabled:
        notes.append(f"环境 {match.key}（{match.title}）已停用，排查工具会拒绝调用。")
    return _envelope(
        summary=f"environment {match.key}",
        rows=rows,
        stats={
            "environment": match.key,
            "title": match.title,
            "targets": len(rows),
            "enabled": sum(1 for row in rows if row["enabled"]),
        },
        notes=notes,
    )


def _envelope(
    *,
    summary: str,
    rows: list[dict[str, Any]],
    stats: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "target": "*",
        "type": "all",
        "summary": summary,
        "time_range": None,
        "returned": len(rows),
        "truncated": False,
        "truncation": None,
        "elapsed_ms": 0,
        "rows": rows,
        "stats": stats,
        "notes": notes,
    }


def _iso(value) -> str | None:
    return (
        value.isoformat(timespec="seconds").replace("+00:00", "Z")
        if value is not None
        else None
    )
