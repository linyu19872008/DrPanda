from __future__ import annotations

from fastmcp import Client

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_server


async def test_mcp_in_process_client_connects(runtime: Runtime) -> None:
    """M1 还没有业务工具，工具清单应为空；M3 起断言具体工具名。"""
    server = create_server(runtime.config, runtime)
    async with Client(server) as client:
        tools = await client.list_tools()

    assert tools == []
