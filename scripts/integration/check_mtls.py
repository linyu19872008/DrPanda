"""mTLS：MySQL REQUIRE X509 与 ES 客户端证书认证。"""

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
        tls = await call(client, "mysql_query", {
            "target": "drpanda-mysql-mtls",
            "sql": "SHOW STATUS LIKE 'Ssl_cipher'",
        })
        cipher = tls["rows"][0]["Value"]
        print("mysql mTLS cipher:", cipher)
        passed += 1 if cipher else 0
        failed += 0 if cipher else 1

        try:
            await call(client, "mysql_query", {
                "target": "drpanda-mysql-mtls-nocert",
                "sql": "SHOW STATUS LIKE 'Ssl_cipher'",
            })
            print("mysql no client cert: FAIL (unexpected success)")
            failed += 1
        except ToolError as exc:
            ok = str(exc).startswith("UPSTREAM_UNAVAILABLE")
            print("mysql no client cert:", str(exc)[:140])
            passed += 1 if ok else 0
            failed += 0 if ok else 1

        es_rows = await call(client, "es_search", {
            "target": "drpanda-es-mtls",
            "index": "drpanda-logs",
            "query": '{"match_all":{}}',
        })
        print("es mTLS:", [row.get("message") for row in es_rows["rows"]])
        passed += 1 if es_rows["returned"] >= 1 else 0
        failed += 0 if es_rows["returned"] >= 1 else 1

        try:
            await call(client, "es_search", {
                "target": "drpanda-es-mtls-nocert",
                "index": "drpanda-logs",
                "query": '{"match_all":{}}',
            })
            print("es no client cert: FAIL (unexpected success)")
            failed += 1
        except ToolError as exc:
            ok = str(exc).startswith("UPSTREAM_UNAVAILABLE")
            print("es no client cert:", str(exc)[:140])
            passed += 1 if ok else 0
            failed += 0 if ok else 1

    print(f"SUMMARY pass={passed} fail={failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
