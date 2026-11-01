from __future__ import annotations

from fastmcp import Client

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_server


async def test_systems_status_tool_listed(runtime: Runtime) -> None:
    server = create_server(runtime.config, runtime)
    async with Client(server) as client:
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == ["systems_status"]
    assert tools[0].annotations is not None
    assert tools[0].annotations.read_only_hint is True


async def test_systems_status_returns_envelope(runtime: Runtime) -> None:
    server = create_server(runtime.config, runtime)
    async with Client(server) as client:
        result = await client.call_tool("systems_status", {})

    payload = result.structured_content
    assert payload is not None
    assert set(payload) == {
        "target",
        "type",
        "summary",
        "time_range",
        "returned",
        "truncated",
        "truncation",
        "elapsed_ms",
        "rows",
        "stats",
        "notes",
    }
    assert payload["target"] == "*"
    assert payload["type"] == "all"
    assert payload["rows"] == []
    assert payload["stats"] == {"targets": 0, "enabled": 0}
