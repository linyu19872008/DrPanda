"""P1：MySQL TLS 与 ES 多 host 故障切换（本机 Docker）。"""

import asyncio
import subprocess

import httpx
from fastmcp import Client
from fastmcp.exceptions import ToolError

MCP = "http://127.0.0.1:8111/mcp"


def compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", "scripts/integration/compose.yaml", *args],
        check=False,
        capture_output=True,
    )


async def call(client, tool, args):
    return (await client.call_tool(tool, args)).structured_content


async def wait_es() -> None:
    async with httpx.AsyncClient(
        auth=("elastic", "drpanda_es_pw"), timeout=2
    ) as client:
        for _ in range(60):
            try:
                response = await client.get("http://127.0.0.1:19200/_cluster/health")
                if response.status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
    raise RuntimeError("Elasticsearch 未就绪")


async def main() -> None:
    passed = 0
    failed = 0
    compose("start", "elasticsearch", "elasticsearch-2")
    await wait_es()
    async with Client(MCP) as client:
        # MySQL TLS
        tls = await call(client, "mysql_query", {
            "target": "drpanda-mysql-tls",
            "sql": "SHOW STATUS LIKE 'Ssl_cipher'",
        })
        plain = await call(client, "mysql_query", {
            "target": "drpanda-mysql",
            "sql": "SHOW STATUS LIKE 'Ssl_cipher'",
        })
        tls_cipher = tls["rows"][0]["Value"]
        plain_cipher = plain["rows"][0]["Value"]
        print("mysql TLS cipher:", tls_cipher)
        print("mysql plain cipher:", repr(plain_cipher))
        if tls_cipher and not plain_cipher:
            passed += 1
        else:
            failed += 1
            print("FAIL mysql tls")

        # ES multi-host: both up -> first host
        before = await call(client, "es_search", {
            "target": "drpanda-es-multi", "index": "drpanda-logs",
            "query": '{"match_all":{}}',
        })
        print("es multi before:", [row.get("message") for row in before["rows"]])
        if before["returned"] >= 1:
            passed += 1
        else:
            failed += 1

        # 停第一个节点，验证 failover
        compose("stop", "elasticsearch")
        await asyncio.sleep(2)
        after = await call(client, "es_search", {
            "target": "drpanda-es-multi", "index": "drpanda-logs",
            "query": '{"match_all":{}}',
        })
        health = await call(client, "es_health", {"target": "drpanda-es-multi"})
        print("es failover:", [row.get("message") for row in after["rows"]], health["stats"]["status"])
        if after["returned"] >= 1 and health["stats"]["status"] == "green":
            passed += 1
        else:
            failed += 1
            print("FAIL es failover")

        # 两个节点都停，验证统一错误
        compose("stop", "elasticsearch-2")
        await asyncio.sleep(2)
        try:
            await call(client, "es_search", {
                "target": "drpanda-es-multi", "index": "drpanda-logs",
                "query": '{"match_all":{}}',
            })
            print("FAIL es both down: unexpected success")
            failed += 1
        except ToolError as exc:
            print("es both down:", str(exc).split(":", 1)[0])
            if str(exc).startswith("UPSTREAM_UNAVAILABLE"):
                passed += 1
            else:
                failed += 1

    compose("start", "elasticsearch", "elasticsearch-2")
    await wait_es()
    print(f"SUMMARY pass={passed} fail={failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
