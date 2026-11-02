import asyncio
import json
import os

BASE_URL = os.environ.get("DRPANDA_BASE_URL", "http://127.0.0.1:8111")
MCP_URL = os.environ.get("DRPANDA_MCP_URL", BASE_URL + "/mcp")
from fastmcp import Client
from fastmcp.exceptions import ToolError

CHECKS = [
    ("mysql", "mysql_tables", {"target": "drpanda-mysql"}),
    ("mysql", "mysql_describe", {"target": "drpanda-mysql", "table": "orders"}),
    ("mysql", "mysql_query", {"target": "drpanda-mysql", "sql": "SELECT id, status, amount FROM orders WHERE status = 'paid' ORDER BY id LIMIT 50"}),
    ("mysql", "mysql_explain", {"target": "drpanda-mysql", "sql": "SELECT * FROM orders WHERE status = 'paid' LIMIT 5"}),
    ("mysql", "mysql_processlist", {"target": "drpanda-mysql"}),
    ("mongo", "mongo_collections", {"target": "drpanda-mongo", "db": "drpanda"}),
    ("mongo", "mongo_find", {"target": "drpanda-mongo", "db": "drpanda", "collection": "drpanda_orders", "filter": '{"status":"paid"}'}),
    ("mongo", "mongo_aggregate", {"target": "drpanda-mongo", "db": "drpanda", "collection": "drpanda_orders", "pipeline": '[{"$match":{"status":"paid"}},{"$group":{"_id":"$status","count":{"$sum":1}}}]'}),
    ("mongo", "mongo_stats", {"target": "drpanda-mongo", "db": "drpanda", "collection": "drpanda_orders"}),
    ("es", "es_mapping", {"target": "drpanda-es", "index": "drpanda-logs"}),
    ("es", "es_search", {"target": "drpanda-es", "index": "drpanda-logs", "query": '{"match":{"message":"integration"}}'}),
    ("es", "es_health", {"target": "drpanda-es"}),
    ("es", "es_index_stats", {"target": "drpanda-es", "index": "drpanda-logs"}),
    ("redis", "redis_get", {"target": "drpanda-redis", "key": "drpanda:order:1"}),
    ("redis", "redis_scan", {"target": "drpanda-redis", "pattern": "drpanda:*"}),
    ("redis", "redis_info", {"target": "drpanda-redis", "section": "server"}),
    ("redis", "redis_slowlog", {"target": "drpanda-redis", "count": 10}),
    ("rabbit", "rabbit_queues", {"target": "drpanda-rabbit"}),
    ("rabbit", "rabbit_queue", {"target": "drpanda-rabbit", "vhost": "/", "queue": "drpanda-orders"}),
]

async def main():
    results = []
    async with Client(MCP_URL) as c:
        tools = sorted(t.name for t in await c.list_tools())
        print("tools:", len(tools))
        print("systems:", json.dumps((await c.call_tool("systems_status", {})).structured_content["stats"], ensure_ascii=False))
        for component, tool, args in CHECKS:
            try:
                r = await c.call_tool(tool, args)
                data = r.structured_content or {}
                summary = {
                    "tool": tool,
                    "returned": data.get("returned"),
                    "truncated": data.get("truncated"),
                    "elapsed_ms": data.get("elapsed_ms"),
                    "rows_sample": data.get("rows", [])[:2],
                    "stats": data.get("stats"),
                }
                results.append((component, tool, "PASS", summary))
                print("PASS", tool, json.dumps(summary, ensure_ascii=False)[:500])
            except ToolError as exc:
                results.append((component, tool, "FAIL", str(exc)))
                print("FAIL", tool, str(exc)[:500])
    print("\nSUMMARY")
    for component, tool, status, detail in results:
        print(f"{component:7s} {tool:18s} {status}")
    failures = [r for r in results if r[2] == "FAIL"]
    print("failures:", len(failures))

asyncio.run(main())
