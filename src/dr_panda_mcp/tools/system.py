"""`systems_status`：列出已登记目标与最近连通性（planning 8.4 / 8.9）。"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from dr_panda_mcp.connectors import base
from dr_panda_mcp.runtime import Runtime


def register_systems_status(server: FastMCP, runtime: Runtime) -> None:
    @server.tool(annotations={"readOnlyHint": True})
    async def systems_status() -> dict[str, Any]:
        """列出已登记目标、启用状态与最近一次连通性测试结果。"""
        with base.Stopwatch() as watch:
            targets = await runtime.store.list_all()

        rows: list[dict[str, Any]] = []
        for target in targets:
            rows.append(
                {
                    "name": target.name,
                    "type": target.type,
                    "enabled": target.enabled,
                    "last_test_at": _iso(target.last_test_at),
                    "last_test_ok": target.last_test_ok,
                    "last_test_error": target.last_test_error,
                }
            )

        return {
            "target": "*",
            "type": "all",
            "summary": "systems_status",
            "time_range": None,
            "returned": len(rows),
            "truncated": False,
            "truncation": None,
            "elapsed_ms": watch.elapsed_ms,
            "rows": rows,
            "stats": {
                "targets": len(rows),
                "enabled": sum(1 for row in rows if row["enabled"]),
            },
            "notes": [],
        }


def _iso(value) -> str | None:
    return (
        value.isoformat(timespec="seconds").replace("+00:00", "Z")
        if value is not None
        else None
    )
