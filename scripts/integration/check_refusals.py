import asyncio
import os

BASE_URL = os.environ.get("DRPANDA_BASE_URL", "http://127.0.0.1:8111")
MCP_URL = os.environ.get("DRPANDA_MCP_URL", BASE_URL + "/mcp")
from fastmcp import Client
from fastmcp.exceptions import ToolError

CASES = [
    ("mysql dangerous", "mysql_query", {"target": "drpanda-mysql", "sql": "SELECT SLEEP(10)"}),
    ("mysql system schema", "mysql_query", {"target": "drpanda-mysql", "sql": "SELECT * FROM mysql.user LIMIT 1"}),
    ("mongo no match", "mongo_aggregate", {"target": "drpanda-mongo", "db": "drpanda", "collection": "drpanda_orders", "pipeline": '[{"$group":{"_id":"$status"}}]'}),
    ("mongo scope", "mongo_find", {"target": "drpanda-mongo", "db": "other", "collection": "x", "filter": '{"a":1}'}),
    ("es script", "es_search", {"target": "drpanda-es", "index": "drpanda-logs", "query": '{"script":{"script":{"source":"1"}}}'}),
    ("es scope", "es_search", {"target": "drpanda-es", "index": "other", "query": '{"match_all":{}}'}),
    ("redis scope", "redis_get", {"target": "drpanda-redis", "key": "other:1"}),
    ("redis scan too large", "redis_scan", {"target": "drpanda-redis", "pattern": "drpanda:*", "count": 500}),
    ("rabbit vhost scope", "rabbit_queues", {"target": "drpanda-rabbit", "vhost": "other"}),
]

async def main():
    async with Client(MCP_URL) as c:
        for label, tool, args in CASES:
            try:
                await c.call_tool(tool, args)
                print("UNEXPECTED PASS", label)
            except ToolError as exc:
                print("EXPECTED", label, "->", str(exc).split(":", 1)[0])

asyncio.run(main())
