from __future__ import annotations

from fastmcp import Client

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_server


async def test_mcp_in_process_client_connects(runtime: Runtime) -> None:
    """M3 起工具清单有 systems_status。"""
    server = create_server(runtime.config, runtime)
    async with Client(server) as client:
        tools = await client.list_tools()

    names = sorted(tool.name for tool in tools)
    assert "systems_status" in names
    assert "cls_search" in names and "gitlab_blame" in names
