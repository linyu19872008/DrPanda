#!/usr/bin/env python3
"""冒烟：启动服务 → 探 ``/healthz`` → 用 MCP 客户端连 ``/mcp`` 调 ``systems_status``。

用法：``uv run python scripts/smoke.py``
退出码 0 表示通过；非 0 表示启动、健康检查或 MCP 调用失败。
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTUP_TIMEOUT_SECONDS = 20
POLL_INTERVAL_SECONDS = 0.2


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_healthz(url: str, process: subprocess.Popen[str]) -> dict:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_error: object = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"服务进程提前退出（code={process.returncode}）：\n{process.stderr.read()}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"等待 {url} 超时，最后一次错误：{last_error}")


async def _check_mcp(mcp_url: str) -> dict:
    from fastmcp import Client

    async with Client(mcp_url) as client:
        tools = await client.list_tools()
        names = sorted(tool.name for tool in tools)
        if "systems_status" not in names:
            raise RuntimeError(f"工具清单里没有 systems_status：{names}")
        result = await client.call_tool("systems_status", {})
        payload = result.structured_content or result.data
        if not isinstance(payload, dict):
            raise TypeError("systems_status 没有返回结构化结果")
        if payload.get("target") != "*" or payload.get("type") != "all":
            raise RuntimeError(f"systems_status 包络不合法：{payload}")
        return {
            "tools": names,
            "returned": payload.get("returned"),
            "stats": payload.get("stats"),
        }


def main() -> int:
    port = _free_port()
    env = dict(os.environ)
    env["DR_PANDA_HOST"] = "127.0.0.1"
    env["DR_PANDA_PORT"] = str(port)
    env["DR_PANDA_LOG_LEVEL"] = "WARNING"
    env.pop("DR_PANDA_SECRET_KEY", None)

    process = subprocess.Popen(
        [sys.executable, "-m", "dr_panda_mcp"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        payload = _wait_healthz(f"http://127.0.0.1:{port}/healthz", process)
        if payload.get("ok") is not True or payload.get("db") != "ok":
            print(f"健康检查返回值不合法：{payload}", file=sys.stderr)
            return 1

        mcp = asyncio.run(_check_mcp(f"http://127.0.0.1:{port}/mcp"))
        print(f"健康检查通过：{payload}")
        print(f"MCP 检查通过：{mcp}")
        return 0
    except Exception as exc:  # noqa: BLE001 - 冒烟脚本需要打印所有失败原因
        print(f"冒烟失败：{exc}", file=sys.stderr)
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
