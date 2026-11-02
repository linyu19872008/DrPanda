import asyncio
import os
import sys

from fastmcp import Client
from fastmcp.exceptions import ToolError

BASE = os.environ.get("DRPANDA_MCP_URL", "http://127.0.0.1:8111/mcp")
results = []

ENVELOPE = {"target","type","summary","time_range","returned","truncated","truncation","elapsed_ms","rows","stats","notes"}

async def call(c, tool, args):
    r = await c.call_tool(tool, args)
    data = r.structured_content
    assert data is not None
    missing = ENVELOPE - set(data)
    assert not missing, f"{tool} missing envelope keys {missing}"
    return data

def mark(label, tool, ok, detail=""):
    results.append((label, tool, "PASS" if ok else "FAIL", detail))
    print(("PASS" if ok else "FAIL"), f"{label:24s}", tool, detail[:240])

async def ok(c, label, tool, args, predicate=None):
    try:
        data = await call(c, tool, args)
        if predicate:
            assert predicate(data), f"predicate failed: {data}"
        mark(label, tool, True, f"returned={data.get('returned')} truncated={data.get('truncated')}")
    except Exception as exc:  # noqa: BLE001 - 测试脚本需要把任何失败记成一条
        mark(label, tool, False, f"{type(exc).__name__}: {exc}")

async def err(c, label, tool, args, code):
    try:
        await call(c, tool, args)
        mark(label, tool, False, "unexpected success")
    except ToolError as exc:
        text = str(exc)
        if text.startswith(code):
            mark(label, tool, True, text[:160])
        else:
            mark(label, tool, False, f"expected {code}, got {text[:200]}")
    except Exception as exc:  # noqa: BLE001 - 测试脚本需要把任何失败记成一条
        mark(label, tool, False, f"{type(exc).__name__}: {exc}")

async def main():
    async with Client(BASE) as c:
        # MySQL
        await ok(c, "mysql tables", "mysql_tables", {"target":"drpanda-mysql"}, lambda d: d["returned"] == 2)
        await ok(c, "mysql tables other db", "mysql_tables", {"target":"drpanda-mysql-wide","db":"drpanda_archive"}, lambda d: d["returned"] == 1)
        await ok(c, "mysql describe", "mysql_describe", {"target":"drpanda-mysql","table":"orders"}, lambda d: d["returned"] == 5)
        await ok(c, "mysql describe view", "mysql_describe", {"target":"drpanda-mysql","table":"order_view"}, lambda d: d["returned"] == 3)
        await ok(c, "mysql query mixed types", "mysql_query", {"target":"drpanda-mysql","sql":"SELECT id,status,amount,note,created_at FROM orders WHERE id=1"}, lambda d: d["returned"] == 1)
        await ok(c, "mysql query empty", "mysql_query", {"target":"drpanda-mysql","sql":"SELECT * FROM orders WHERE status='nope'"}, lambda d: d["returned"] == 0)
        await ok(c, "mysql query archive", "mysql_query", {"target":"drpanda-mysql-wide","sql":"SELECT * FROM drpanda_archive.orders WHERE status='paid'"}, lambda d: d["returned"] == 1)
        await ok(c, "mysql explain", "mysql_explain", {"target":"drpanda-mysql","sql":"SELECT * FROM orders WHERE status='paid'"}, lambda d: d["returned"] >= 1)
        await ok(c, "mysql processlist", "mysql_processlist", {"target":"drpanda-mysql"}, lambda d: d["returned"] >= 1)
        await ok(c, "mysql truncation", "mysql_query", {"target":"drpanda-mysql-small","sql":"SELECT * FROM orders WHERE status='paid'"}, lambda d: d["returned"] == 1 and d["truncated"] is True)
        await err(c, "mysql write", "mysql_query", {"target":"drpanda-mysql","sql":"UPDATE orders SET status='x' WHERE id=1"}, "GUARD_REJECTED")
        await err(c, "mysql multi stmt", "mysql_query", {"target":"drpanda-mysql","sql":"SELECT 1; DROP TABLE orders"}, "GUARD_REJECTED")
        await err(c, "mysql system schema", "mysql_query", {"target":"drpanda-mysql","sql":"SELECT * FROM mysql.user"}, "DANGEROUS_OPERATION")
        await err(c, "mysql cross db", "mysql_query", {"target":"drpanda-mysql","sql":"SELECT * FROM drpanda_archive.orders"}, "SCOPE_DENIED")
        await err(c, "mysql show databases", "mysql_query", {"target":"drpanda-mysql","sql":"SHOW DATABASES"}, "SCOPE_DENIED")
        await err(c, "mysql unknown table", "mysql_query", {"target":"drpanda-mysql","sql":"SELECT * FROM orders_missing WHERE id=1"}, "UPSTREAM_UNAVAILABLE")
        await err(c, "mysql bad creds", "mysql_tables", {"target":"drpanda-mysql-bad"}, "UPSTREAM_UNAVAILABLE")

        # Mongo
        await ok(c, "mongo collections", "mongo_collections", {"target":"drpanda-mongo","db":"drpanda"}, lambda d: d["returned"] >= 1)
        await ok(c, "mongo find projection/sort", "mongo_find", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","filter":'{"status":"paid"}',"projection":'{"_id":0,"order_id":1,"status":1}',"sort":'{"order_id":-1}',"limit":1}, lambda d: d["returned"] == 1 and "_id" not in d["rows"][0])
        await ok(c, "mongo find empty", "mongo_find", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","filter":'{"status":"nope"}'}, lambda d: d["returned"] == 0)
        await ok(c, "mongo aggregate variants", "mongo_aggregate", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","pipeline":'[{"$match":{"status":"paid"}},{"$project":{"_id":0,"status":1,"amount":1}},{"$sort":{"amount":-1}},{"$limit":1}]'}, lambda d: d["returned"] == 1)
        await ok(c, "mongo aggregate lookup", "mongo_aggregate", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","pipeline":'[{"$match":{"status":"paid"}},{"$lookup":{"from":"drpanda_events","localField":"order_id","foreignField":"order_id","as":"events"}}]'}, lambda d: d["returned"] >= 1)
        await ok(c, "mongo stats coll", "mongo_stats", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders"}, lambda d: d["returned"] == 1)
        await ok(c, "mongo stats db", "mongo_stats", {"target":"drpanda-mongo","db":"drpanda"}, lambda d: d["returned"] == 1)
        await ok(c, "mongo truncation", "mongo_find", {"target":"drpanda-mongo-small","db":"drpanda","collection":"drpanda_orders","filter":'{"status":{"$in":["paid","refunded"]}}'}, lambda d: d["returned"] == 2 and d["truncated"] is True)
        await err(c, "mongo no filter", "mongo_find", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","filter":"{}"}, "GUARD_REJECTED")
        await err(c, "mongo group no match", "mongo_aggregate", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","pipeline":'[{"$group":{"_id":"$status"}}]'}, "DANGEROUS_OPERATION")
        await err(c, "mongo $out", "mongo_aggregate", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","pipeline":'[{"$match":{"status":"paid"}},{"$out":"x"}]'}, "DANGEROUS_OPERATION")
        await err(c, "mongo $where", "mongo_find", {"target":"drpanda-mongo","db":"drpanda","collection":"drpanda_orders","filter":'{"$where":"1"}'}, "DANGEROUS_OPERATION")
        await err(c, "mongo db scope", "mongo_find", {"target":"drpanda-mongo","db":"other","collection":"x","filter":'{"a":1}'}, "SCOPE_DENIED")
        await err(c, "mongo bad creds", "mongo_collections", {"target":"drpanda-mongo-bad","db":"drpanda"}, "UPSTREAM_UNAVAILABLE")

        # ES
        await ok(c, "es nested mapping", "es_mapping", {"target":"drpanda-es-wide","index":"drpanda-nested"}, lambda d: d["returned"] >= 3 and any(row["field"] == "payload.code" for row in d["rows"]))
        await ok(c, "es empty mapping", "es_mapping", {"target":"drpanda-es-wide","index":"drpanda-empty"}, lambda d: d["returned"] == 1)
        await ok(c, "es search match", "es_search", {"target":"drpanda-es","index":"drpanda-logs","query":'{"match":{"message":"integration"}}'}, lambda d: d["returned"] >= 1)
        await ok(c, "es search page/sort", "es_search", {"target":"drpanda-es","index":"drpanda-logs","query":'{"match_all":{}}',"from":1,"size":2,"sort":'[{"ts":"desc"}]'}, lambda d: d["returned"] == 2)
        await ok(c, "es search empty", "es_search", {"target":"drpanda-es-wide","index":"drpanda-empty","query":'{"match_all":{}}'}, lambda d: d["returned"] == 0)
        await ok(c, "es health", "es_health", {"target":"drpanda-es"}, lambda d: d["stats"]["status"] in ("green","yellow"))
        await ok(c, "es index stats", "es_index_stats", {"target":"drpanda-es","index":"drpanda-logs"}, lambda d: d["returned"] == 1)
        await ok(c, "es truncation", "es_search", {"target":"drpanda-es-small","index":"drpanda-logs","query":'{"match_all":{}}'}, lambda d: d["returned"] == 2 and d["truncated"] is True)
        await err(c, "es size over limit", "es_search", {"target":"drpanda-es-small","index":"drpanda-logs","query":'{"match_all":{}}',"size":3}, "DANGEROUS_OPERATION")
        await err(c, "es deep from", "es_search", {"target":"drpanda-es","index":"drpanda-logs","query":'{"match_all":{}}',"from":10000,"size":1}, "DANGEROUS_OPERATION")
        await err(c, "es script", "es_search", {"target":"drpanda-es","index":"drpanda-logs","query":'{"script":{"script":{"source":"1"}}}'}, "DANGEROUS_OPERATION")
        await err(c, "es terms agg", "es_search", {"target":"drpanda-es","index":"drpanda-logs","query":'{"match_all":{},"aggs":{"x":{"terms":{"field":"service","size":1000}}}}'}, "DANGEROUS_OPERATION")
        await err(c, "es invalid query body", "es_search", {"target":"drpanda-es","index":"drpanda-logs","query":'{"match_all":{},"track_total_hits":true}'}, "UPSTREAM_UNAVAILABLE")
        await err(c, "es index scope", "es_search", {"target":"drpanda-es","index":"other","query":'{"match_all":{}}'}, "SCOPE_DENIED")
        await err(c, "es bad creds", "es_search", {"target":"drpanda-es-bad","index":"drpanda-logs","query":'{"match_all":{}}'}, "UPSTREAM_UNAVAILABLE")

        # Redis
        for label, key in [("redis string","drpanda:order:1"),("redis list","drpanda:list"),("redis set","drpanda:set"),("redis zset","drpanda:zset"),("redis hash","drpanda:hash"),("redis ttl","drpanda:ttl")]:
            await ok(c, label, "redis_get", {"target":"drpanda-redis","key":key})
        await ok(c, "redis missing", "redis_get", {"target":"drpanda-redis","key":"drpanda:missing"}, lambda d: d["rows"][0]["type"] == "none")
        await ok(c, "redis scan page", "redis_scan", {"target":"drpanda-redis","pattern":"drpanda:*","count":2}, lambda d: d["returned"] >= 1)
        await ok(c, "redis info all", "redis_info", {"target":"drpanda-redis"}, lambda d: bool(d["stats"]))
        await ok(c, "redis slowlog prefix", "redis_slowlog", {"target":"drpanda-redis","count":20}, lambda d: all("other" not in str(row.get("command")) for row in d["rows"]))
        await ok(c, "redis scan truncation", "redis_scan", {"target":"drpanda-redis-small","pattern":"drpanda:*","count":10}, lambda d: d["returned"] == 2 and d["truncated"] is True)
        await err(c, "redis huge string", "redis_get", {"target":"drpanda-redis","key":"drpanda:huge"}, "DANGEROUS_OPERATION")
        await err(c, "redis big list", "redis_get", {"target":"drpanda-redis","key":"drpanda:biglist"}, "DANGEROUS_OPERATION")
        await err(c, "redis prefix scope", "redis_get", {"target":"drpanda-redis","key":"other:1"}, "SCOPE_DENIED")
        await err(c, "redis scan count", "redis_scan", {"target":"drpanda-redis","pattern":"drpanda:*","count":500}, "DANGEROUS_OPERATION")
        await err(c, "redis bad creds", "redis_get", {"target":"drpanda-redis-bad","key":"drpanda:order:1"}, "UPSTREAM_UNAVAILABLE")

        # Rabbit
        await ok(c, "rabbit queues messages", "rabbit_queues", {"target":"drpanda-rabbit"}, lambda d: d["returned"] >= 4 and any(row["messages"] >= 2 for row in d["rows"]))
        await ok(c, "rabbit queue detail", "rabbit_queue", {"target":"drpanda-rabbit","vhost":"/","queue":"drpanda-orders"}, lambda d: d["rows"][0]["messages"] >= 2)
        await ok(c, "rabbit extra vhost", "rabbit_queues", {"target":"drpanda-rabbit-wide","vhost":"drpanda-extra"}, lambda d: d["returned"] == 1)
        await ok(c, "rabbit truncation", "rabbit_queues", {"target":"drpanda-rabbit-small"}, lambda d: d["returned"] == 2 and d["truncated"] is True)
        await err(c, "rabbit missing queue", "rabbit_queue", {"target":"drpanda-rabbit","vhost":"/","queue":"drpanda-missing"}, "UPSTREAM_NOT_FOUND")
        await err(c, "rabbit vhost scope", "rabbit_queues", {"target":"drpanda-rabbit","vhost":"drpanda-extra"}, "SCOPE_DENIED")
        await err(c, "rabbit bad creds", "rabbit_queues", {"target":"drpanda-rabbit-bad"}, "UPSTREAM_UNAVAILABLE")

    print("\nSUMMARY")
    failures = [r for r in results if r[2] == "FAIL"]
    print(f"total={len(results)} pass={len(results)-len(failures)} fail={len(failures)}")
    for label, tool, status, detail in failures:
        print("FAIL", label, tool, detail[:300])
    sys.exit(1 if failures else 0)

asyncio.run(main())
