"""MCP 排查工具。"""

from __future__ import annotations

from fastmcp import FastMCP

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.tools.system import register_systems_status


def register_tools(server: FastMCP, runtime: Runtime) -> None:
    register_systems_status(server, runtime)


__all__ = ["register_tools"]
