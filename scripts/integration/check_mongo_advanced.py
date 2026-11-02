"""Mongo X.509 与 replica set 检查（Docker 可落地部分）。"""

import asyncio

from fastmcp import Client
from fastmcp.exceptions import ToolError

MCP = "http://127.0.0.1:8111/mcp"


async def call(client, tool, args):
    return (await client.call_tool(tool, args)).structured_content


async def find(client, target):
    return await call(client, "mongo_find", {
        "target": target, "db": "drpanda",
        "collection": "drpanda_orders", "filter": '{"status":"paid"}',
    })


async def main() -> None:
    passed = 0
    failed = 0
    async with Client(MCP) as client:
        for label, target in [
            ("x509", "drpanda-mongo-x509"),
            ("replica-set", "drpanda-mongo-replset"),
        ]:
            try:
                data = await find(client, target)
                ok = data["returned"] >= 1
                print(label, "PASS" if ok else "FAIL", data["returned"])
                passed += 1 if ok else 0
                failed += 0 if ok else 1
            except ToolError as exc:
                print(label, "FAIL", str(exc)[:180])
                failed += 1

        try:
            await find(client, "drpanda-mongo-x509-nocert")
            print("x509 no cert: FAIL (unexpected success)")
            failed += 1
        except ToolError as exc:
            ok = str(exc).startswith("UPSTREAM_UNAVAILABLE")
            print("x509 no cert:", str(exc)[:180])
            passed += 1 if ok else 0
            failed += 0 if ok else 1

    print(f"SUMMARY pass={passed} fail={failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
