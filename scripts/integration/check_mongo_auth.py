"""Mongo 认证模式与 TLS 检查。"""

import asyncio

from fastmcp import Client
from fastmcp.exceptions import ToolError

MCP = "http://127.0.0.1:8111/mcp"
CASES = [
    ("noauth", "drpanda-mongo-noauth", "collections"),
    ("password", "drpanda-mongo", "find"),
    ("uri", "drpanda-mongo-uri", "find"),
    ("tls", "drpanda-mongo-tls", "find"),
    ("mtls", "drpanda-mongo-mtls", "find"),
]


async def call(client, tool, args):
    return (await client.call_tool(tool, args)).structured_content


async def main() -> None:
    passed = 0
    failed = 0
    async with Client(MCP) as client:
        for label, target, mode in CASES:
            try:
                if mode == "collections":
                    data = await call(client, "mongo_collections", {
                        "target": target, "db": "drpanda",
                    })
                    ok = data["returned"] >= 1
                else:
                    data = await call(client, "mongo_find", {
                        "target": target, "db": "drpanda",
                        "collection": "drpanda_orders", "filter": '{"status":"paid"}',
                    })
                    ok = data["returned"] >= 1
                print(f"{label}:", "PASS" if ok else "FAIL", data["returned"])
                passed += 1 if ok else 0
                failed += 0 if ok else 1
            except ToolError as exc:
                print(f"{label}: FAIL {str(exc)[:160]}")
                failed += 1

        for label, target, code in [
            ("tls no CA", "drpanda-mongo-tls-noca", "UPSTREAM_UNAVAILABLE"),
            ("mtls no cert", "drpanda-mongo-mtls-nocert", "UPSTREAM_UNAVAILABLE"),
        ]:
            try:
                await call(client, "mongo_find", {
                    "target": target, "db": "drpanda",
                    "collection": "drpanda_orders", "filter": '{"status":"paid"}',
                })
                print(f"{label}: FAIL (unexpected success)")
                failed += 1
            except ToolError as exc:
                ok = str(exc).startswith(code)
                print(f"{label}:", str(exc)[:160])
                passed += 1 if ok else 0
                failed += 0 if ok else 1

    print(f"SUMMARY pass={passed} fail={failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
