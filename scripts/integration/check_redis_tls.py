"""Redis ACL + TLS / mTLS 检查。"""

import asyncio

from fastmcp import Client
from fastmcp.exceptions import ToolError

MCP = "http://127.0.0.1:8111/mcp"


async def call(client, tool, args):
    return (await client.call_tool(tool, args)).structured_content


async def main() -> None:
    passed = 0
    failed = 0
    async with Client(MCP) as client:
        for label, target in [
            ("acl-tls", "drpanda-redis-acl-tls"),
            ("acl-mtls", "drpanda-redis-acl-mtls"),
        ]:
            try:
                data = await call(client, "redis_get", {
                    "target": target, "key": "drpanda:order:1",
                })
                ok = data["rows"][0]["value"] == "paid"
                print(label, "PASS" if ok else "FAIL", data["rows"])
                passed += 1 if ok else 0
                failed += 0 if ok else 1
            except ToolError as exc:
                print(label, "FAIL", str(exc)[:180])
                failed += 1

        try:
            await call(client, "redis_get", {
                "target": "drpanda-redis-mtls-nocert", "key": "drpanda:order:1",
            })
            print("mtls no cert: FAIL (unexpected success)")
            failed += 1
        except ToolError as exc:
            ok = str(exc).startswith("UPSTREAM_UNAVAILABLE")
            print("mtls no cert:", str(exc)[:180])
            passed += 1 if ok else 0
            failed += 0 if ok else 1

    print(f"SUMMARY pass={passed} fail={failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
