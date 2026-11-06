from __future__ import annotations

import re

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


async def test_mcp_public_text_is_english(runtime: Runtime) -> None:
    server = create_server(runtime.config, runtime)
    async with Client(server) as client:
        tools = await client.list_tools()
        prompt = await client.get_prompt("investigate_error", {"service": "order"})

    texts = [server.instructions or ""]
    texts.extend(tool.description or "" for tool in tools)
    texts.append(prompt.messages[0].content.text)
    texts.extend(str(tool.model_dump()) for tool in tools)
    chinese = [text for text in texts if re.search(r"[\u4e00-\u9fff]", text)]
    assert chinese == [], f"MCP-facing text contains Chinese: {chinese[:2]}"
