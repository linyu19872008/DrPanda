from __future__ import annotations

import sys
import types
from typing import Any

import httpx
import pytest

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import es as es_module
from dr_panda_mcp.connectors import mongo as mongo_module
from dr_panda_mcp.connectors import mysql as mysql_module
from dr_panda_mcp.connectors import redis as redis_module
from dr_panda_mcp.store.protocol import Target
from dr_panda_mcp.tools.data import _mysql_scope, force_limit
from tests.fakes import make_target


def _mysql_target() -> Target:
    return make_target(
        type_="mysql",
        options={
            "host": "127.0.0.1",
            "port": 3306,
            "user": "ro",
            "default_db": "app",
            "allowed_dbs": ["app"],
            "timeout_s": "15",
            "max_rows": 100,
        },
        secret={"password": "pw"},
    )


class _Cursor:
    def __init__(self, statements: list[str]) -> None:
        self.statements = statements
        self.description = [("id",), ("name",)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, statement: str) -> None:
        self.statements.append(statement)

    async def fetchall(self):
        return [(1, "a"), (2, "b")]

    async def fetchone(self):
        return (1,)


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.closed = False

    def cursor(self):
        return _Cursor(self.statements)

    async def ensure_closed(self):
        self.closed = True


async def test_mysql_fetch_rows_sets_session_and_returns_dicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()

    async def fake_connect(asyncmy, target):
        return connection

    monkeypatch.setitem(sys.modules, "asyncmy", types.SimpleNamespace(connect=None))
    monkeypatch.setattr(mysql_module, "_connect", fake_connect)

    target = _mysql_target()
    client = mysql_module.connector.create_client(target)
    rows = await client.fetch_rows("SELECT id, name FROM users LIMIT 2")

    assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert connection.statements[:3] == [
        "SET SESSION TRANSACTION READ ONLY",
        "SET SESSION max_execution_time = 15000",
        "SET SESSION sql_select_limit = 100",
    ]
    assert connection.statements[-1] == "SELECT id, name FROM users LIMIT 2"
    assert connection.closed is True


def test_force_limit_and_mysql_scope() -> None:
    assert "LIMIT 100" in force_limit("SELECT * FROM users", 100)
    capped = force_limit("SELECT * FROM users LIMIT 5000", 100)
    assert "LIMIT 100" in capped
    assert force_limit("SHOW TABLES", 100) == "SHOW TABLES"

    target = make_target(
        type_="mysql", options={"allowed_dbs": ["app"], "default_db": "app"}
    )
    _mysql_scope(target, "SELECT * FROM users", "app")
    _mysql_scope(target, "SELECT * FROM app.users", "app")
    with pytest.raises(errors.ScopeDenied):
        _mysql_scope(target, "SELECT * FROM other.users", "app")
    with pytest.raises(errors.ScopeDenied):
        _mysql_scope(target, "SHOW DATABASES", "app")


def _es_target() -> Target:
    return make_target(
        type_="elasticsearch",
        options={
            "hosts": ["http://es:9200"],
            "allowed_indices": ["logs-2026"],
            "timeout_s": "15",
        },
    )


async def test_es_mapping_search_health_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    client = es_module.connector.create_client(_es_target())
    calls: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, *, body=None):
        calls.append((method, path))
        payloads: dict[str, Any] = {
            "/logs-2026/_mapping": {
                "logs-2026": {
                    "mappings": {
                        "properties": {
                            "message": {"type": "text", "analyzer": "standard"},
                            "ctx": {"properties": {"code": {"type": "keyword"}}},
                        }
                    }
                }
            },
            "/logs-2026/_settings": {
                "logs-2026": {"settings": {"index": {"number_of_shards": "2", "number_of_replicas": "1"}}}
            },
            "/logs-2026/_search": {
                "took": 4,
                "hits": {
                    "total": {"value": 1},
                    "hits": [{"_index": "logs-2026", "_id": "a", "_score": 1.0, "_source": {"message": "boom"}}],
                },
            },
            "/_cluster/health": {"status": "green", "number_of_nodes": 3},
            "/logs-2026/_stats": {
                "indices": {
                    "logs-2026": {
                        "primaries": {"docs": {"count": 5}, "store": {"size_in_bytes": 10}},
                        "total": {"docs": {"count": 5}, "store": {"size_in_bytes": 10}},
                    }
                }
            },
        }
        return httpx.Response(200, json=payloads[path], request=httpx.Request(method, f"http://es:9200{path}"))

    monkeypatch.setattr(client, "_request", fake_request)

    rows, stats = await client.mapping("logs-2026")
    search_rows, search_stats = await client.search("logs-2026", {"query": {"match_all": {}}})
    health = await client.health()
    index_rows = await client.index_stats("logs-2026")

    assert [row["field"] for row in rows] == ["message", "ctx.code"]
    assert stats == {"shards": "2", "replicas": "1"}
    assert search_rows[0]["message"] == "boom"
    assert search_stats == {"total": 1, "took": 4}
    assert health["status"] == "green"
    assert index_rows[0]["total_docs"] == 5


class _FakeRedis:
    def __init__(self) -> None:
        self.kind = "string"
        self.size = 1
        self.closed = False

    async def type(self, key):
        return self.kind

    async def ttl(self, key):
        return -1

    async def get(self, key):
        return "v"

    async def llen(self, key):
        return self.size

    async def lrange(self, key, start, stop):
        return [str(index) for index in range(start, stop + 1)]

    async def scan(self, cursor, match, count):
        return 2, ["pay:1", "pay:2"]

    async def info(self, section):
        return {"redis_version": "7.0"}

    async def slowlog_get(self, count):
        return [{"id": 1, "duration": 1000}]

    async def aclose(self):
        self.closed = True


def _redis_target() -> Target:
    return make_target(
        type_="redis",
        options={"host": "127.0.0.1", "port": 6379, "db": 0, "key_prefix": "pay:"},
    )


async def test_redis_inspect_bounded_and_unbounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    client = redis_module.connector.create_client(_redis_target())
    monkeypatch.setattr(client, "_client", lambda: fake)

    string_row = await client.inspect("pay:1", limit=10)
    assert string_row["value"] == "v"
    assert string_row["type"] == "string"

    fake.kind = "list"
    fake.size = 100
    with pytest.raises(errors.GuardRejected) as excinfo:
        await client.inspect("pay:1", limit=10)
    assert excinfo.value.code == errors.DANGEROUS_OPERATION

    fake.size = 2
    list_row = await client.inspect("pay:1", limit=10)
    assert list_row["value"] == [str(index) for index in range(10)]
    assert fake.closed is True


class _FakeMongoCursor:
    def __init__(self, documents):
        self.documents = documents
        self.sort_value = None
        self.limit_value = None

    def sort(self, pairs):
        self.sort_value = pairs
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def to_list(self, length):
        return self.documents[:length]


class _FakeMongoCollection:
    def __init__(self) -> None:
        self.find_args = None
        self.aggregate_args = None

    def find(self, filter_, projection, max_time_ms=None):
        self.find_args = (filter_, projection, max_time_ms)
        return _FakeMongoCursor([{"_id": "1", "status": "paid"}])

    def aggregate(self, pipeline, maxTimeMS=None):
        self.aggregate_args = (pipeline, maxTimeMS)
        return _FakeMongoCursor([{"status": "paid", "count": 1}])


class _FakeMongoDB:
    def __init__(self, collection) -> None:
        self.collection = collection

    def __getitem__(self, name):
        return self.collection

    async def list_collection_names(self):
        return ["orders"]

    async def command(self, name, *args):
        return {"count": 1, "index_count": 1}


class _FakeMotor:
    def __init__(self) -> None:
        self.collection = _FakeMongoCollection()
        self.db = _FakeMongoDB(self.collection)
        self.closed = False

    def __getitem__(self, name):
        return self.db

    def close(self):
        self.closed = True


def _mongo_target() -> Target:
    return make_target(
        type_="mongo", options={"host": "127.0.0.1", "port": 27017, "allowed_dbs": ["app"]}
    )


async def test_mongo_find_limit_and_aggregate_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeMotor()
    client = mongo_module.connector.create_client(_mongo_target())
    monkeypatch.setattr(client, "_client", lambda: fake)

    rows = await client.find(
        "app", "orders", {"status": "paid"}, {"_id": 0}, {"ts": -1}, 5
    )
    aggregate_rows = await client.aggregate(
        "app", "orders", [{"$match": {"status": "paid"}}], 3
    )

    assert rows == [{"_id": "1", "status": "paid"}]
    assert fake.collection.find_args[0] == {"status": "paid"}
    cursor = fake.collection
    assert aggregate_rows[0]["count"] == 1
    pipeline, _ = cursor.aggregate_args
    assert pipeline[-1] == {"$limit": 3}
    assert fake.closed is True
