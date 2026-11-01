from __future__ import annotations

import pytest

from dr_panda_mcp import errors
from dr_panda_mcp.guards import (
    cls as cls_guard,
)
from dr_panda_mcp.guards import (
    es as es_guard,
)
from dr_panda_mcp.guards import (
    gitlab as gitlab_guard,
)
from dr_panda_mcp.guards import (
    kafka as kafka_guard,
)
from dr_panda_mcp.guards import (
    mongo as mongo_guard,
)
from dr_panda_mcp.guards import (
    mysql as mysql_guard,
)
from dr_panda_mcp.guards import (
    rabbit as rabbit_guard,
)
from dr_panda_mcp.guards import (
    redis as redis_guard,
)
from dr_panda_mcp.guards.protocol import Decision, require

EXPECTED = {
    "allow": None,
    "guard": errors.GUARD_REJECTED,
    "danger": errors.DANGEROUS_OPERATION,
}


def assert_decision(decision: Decision, expected: str) -> None:
    if expected == "allow":
        assert decision.allowed is True, decision
        return
    assert decision.allowed is False, decision
    assert decision.error_code == EXPECTED[expected], decision


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------
MYSQL_CASES = [
    ("SELECT 1", "allow"),
    ("SELECT id FROM orders WHERE id = 1", "allow"),
    ("SHOW TABLES", "allow"),
    ("SHOW COLUMNS FROM orders", "allow"),
    ("SHOW PROCESSLIST", "allow"),
    ("DESCRIBE orders", "allow"),
    ("EXPLAIN SELECT * FROM orders WHERE id = 1", "allow"),
    ("SELECT COUNT(*) FROM orders WHERE status = 'paid'", "allow"),
    ("SELECT * FROM orders WHERE id = 1 ORDER BY id", "allow"),
    ("UPDATE orders SET status = 'x'", "guard"),
    ("DELETE FROM orders", "guard"),
    ("CREATE TABLE t (id INT)", "guard"),
    ("SELECT 1; DROP TABLE orders", "guard"),
    ("CALL p()", "guard"),
    ("SHOW GRANTS", "guard"),
    ("SHOW ENGINE INNODB STATUS", "guard"),
    ("EXPLAIN UPDATE orders SET a = 1", "guard"),
    ("SELECT FROM", "guard"),
    ("", "guard"),
    ("SELECT SLEEP(10)", "danger"),
    ("SELECT BENCHMARK(1000, MD5('a'))", "danger"),
    ("SELECT GET_LOCK('x', 10)", "danger"),
    ("SELECT RELEASE_LOCK('x')", "danger"),
    ("EXPLAIN ANALYZE SELECT * FROM orders", "danger"),
    ("SELECT * FROM orders FOR UPDATE", "danger"),
    ("SELECT * FROM orders LOCK IN SHARE MODE", "danger"),
    ("SELECT * FROM information_schema.tables", "danger"),
    ("SELECT * FROM orders ORDER BY id", "danger"),
    ("SELECT /*!50000 SLEEP(10) */ 1", "danger"),
    ("SELECT 1 /*!50000 UNION SELECT password FROM mysql.user */", "danger"),
    ("SELECT COUNT(*) FROM orders", "danger"),
    ("SELECT DISTINCT status FROM orders", "danger"),
    ("SELECT status FROM orders GROUP BY status", "danger"),
]


@pytest.mark.parametrize(("sql", "expected"), MYSQL_CASES)
def test_mysql_guard(sql: str, expected: str) -> None:
    assert_decision(mysql_guard.check_sql(sql), expected)


# ---------------------------------------------------------------------------
# Mongo
# ---------------------------------------------------------------------------
MONGO_CASES = [
    ("find", {"filter": {"status": "paid"}}, "allow"),
    ("count", {"query": {"status": "paid"}}, "allow"),
    ("ping", {}, "allow"),
    ("currentOp", {}, "allow"),
    ("listCollections", {"nameOnly": True}, "allow"),
    ("insert", {"document": {}}, "guard"),
    ("update", {"updates": []}, "guard"),
    ("find", {}, "guard"),
    ("find", {"filter": {}}, "guard"),
    ("find", {"filter": {"status": "paid"}, "allowDiskUse": True}, "danger"),
    ("find", {"filter": {"status": "paid"}, "hint": "index"}, "danger"),
    ("find", {"filter": {"$where": "this.a == 1"}}, "danger"),
    ("aggregate", {"pipeline": [{"$where": "1"}]}, "danger"),
]

MONGO_PIPELINE_CASES = [
    ([{"$match": {"a": 1}}, {"$group": {"_id": "$a"}}, {"$limit": 10}], "allow"),
    ([{"$match": {"a": 1}}, {"$lookup": {"from": "x", "as": "y"}}], "allow"),
    ([{"$group": {"_id": "$a"}}], "danger"),
    ([{"$lookup": {"from": "x", "as": "y"}}], "danger"),
    ([{"$match": {}}, {"$out": "x"}], "danger"),
    ([{"$match": {}}, {"$merge": "x"}], "danger"),
    ([{"$match": {"$function": {"body": "1"}}}], "danger"),
    ([{"$match": {}}, {"$set": {"a": 1}}], "guard"),
    ([{"$match": {}, "$limit": 1}], "guard"),
    ([], "guard"),
]


@pytest.mark.parametrize(("command", "document", "expected"), MONGO_CASES)
def test_mongo_command_guard(command: str, document: dict, expected: str) -> None:
    assert_decision(mongo_guard.check_mongo_command(command, document), expected)


@pytest.mark.parametrize(("pipeline", "expected"), MONGO_PIPELINE_CASES)
def test_mongo_pipeline_guard(pipeline: list[dict], expected: str) -> None:
    assert_decision(mongo_guard.check_mongo_pipeline(pipeline), expected)


# ---------------------------------------------------------------------------
# Elasticsearch
# ---------------------------------------------------------------------------
ES_CASES = [
    ("GET", "/_cluster/health", None, "allow"),
    ("HEAD", "/orders", None, "allow"),
    ("GET", "/orders/_mapping", None, "allow"),
    ("POST", "/orders/_search", {"query": {"match_all": {}}, "size": 10}, "allow"),
    ("POST", "/orders/_count", {"query": {"term": {"a": 1}}}, "allow"),
    ("PUT", "/orders", None, "guard"),
    ("DELETE", "/orders", None, "guard"),
    ("POST", "/_bulk", {}, "guard"),
    ("GET", "/_all/_search", None, "guard"),
    ("POST", "/orders/_update_by_query", {}, "guard"),
    ("POST", "/orders/_search", None, "guard"),
    ("POST", "/orders/_search", {"script": {"source": "1"}}, "danger"),
    ("POST", "/orders/_search", {"script_fields": {"a": {}}}, "danger"),
    ("POST", "/orders/_search", {"runtime_mappings": {}}, "danger"),
    ("POST", "/orders/_search", {"track_total_hits": True}, "danger"),
    ("POST", "/orders/_search", {"from": 9000, "size": 2000}, "danger"),
    (
        "POST",
        "/orders/_search",
        {"aggs": {"a": {"terms": {"field": "x", "size": 500}}}},
        "danger",
    ),
]


@pytest.mark.parametrize(("method", "path", "body", "expected"), ES_CASES)
def test_es_guard(method: str, path: str, body, expected: str) -> None:
    assert_decision(es_guard.check_http(method, path, body), expected)


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_CASES = [
    ("PING", [], "allow"),
    ("GET", ["k"], "allow"),
    ("MGET", ["a", "b"], "allow"),
    ("SCAN", ["0", "COUNT", "100"], "allow"),
    ("HSCAN", ["h", "0", "COUNT", "10"], "allow"),
    ("LRANGE", ["k", "0", "99"], "allow"),
    ("INFO", [], "allow"),
    ("SLOWLOG", ["GET", "10"], "allow"),
    ("MEMORY", ["USAGE", "k"], "allow"),
    ("SMEMBERS", ["k"], "allow"),
    ("SET", ["k", "v"], "guard"),
    ("DEL", ["k"], "guard"),
    ("KEYS", ["*"], "guard"),
    ("CONFIG", ["GET", "x"], "guard"),
    ("SLOWLOG", ["RESET"], "guard"),
    ("MEMORY", ["STATS"], "guard"),
    ("SCAN", ["0", "COUNT", "abc"], "guard"),
    ("LRANGE", ["k", "10", "5"], "guard"),
    ("SCAN", ["0", "COUNT", "1000"], "danger"),
    ("LRANGE", ["k", "0", "-1"], "danger"),
    ("ZRANGE", ["z", "0", "-1"], "danger"),
]


@pytest.mark.parametrize(("command", "args", "expected"), REDIS_CASES)
def test_redis_guard(command: str, args: list, expected: str) -> None:
    assert_decision(redis_guard.check_redis(command, args), expected)


# ---------------------------------------------------------------------------
# GitLab / RabbitMQ
# ---------------------------------------------------------------------------
HTTP_ONLY_CASES = [
    ("gitlab", gitlab_guard.check_gitlab, "GET", "/api/v4/user", "allow"),
    (
        "gitlab",
        gitlab_guard.check_gitlab,
        "POST",
        "/api/v4/projects/1/issues",
        "guard",
    ),
    ("gitlab", gitlab_guard.check_gitlab, "PUT", "/api/v4/projects/1", "guard"),
    ("rabbit", rabbit_guard.check_rabbit, "GET", "/api/queues", "allow"),
    ("rabbit", rabbit_guard.check_rabbit, "GET", "/api/overview", "allow"),
    (
        "rabbit",
        rabbit_guard.check_rabbit,
        "POST",
        "/api/exchanges/x/publish",
        "guard",
    ),
    ("rabbit", rabbit_guard.check_rabbit, "GET", "/notapi/x", "guard"),
    ("rabbit", rabbit_guard.check_rabbit, "DELETE", "/api/queues/v/q", "guard"),
]


@pytest.mark.parametrize(("label", "checker", "method", "path", "expected"), HTTP_ONLY_CASES)
def test_http_only_guards(label: str, checker, method: str, path: str, expected: str) -> None:
    assert_decision(checker(method, path), expected)


# ---------------------------------------------------------------------------
# Kafka / CLS
# ---------------------------------------------------------------------------
KAFKA_CASES = [
    ("describe_cluster", {}, "allow"),
    ("metadata", {}, "allow"),
    ("fetch", {"partition": 0, "offset": 10, "limit": 5}, "allow"),
    ("list_offsets", {"topic": "orders"}, "allow"),
    ("fetch", {"partition": 0, "offset": 10}, "guard"),
    ("fetch", {"partition": 0, "offset": -1, "limit": 5}, "guard"),
    ("get_unknown", {}, "guard"),
    ("create_topics", {}, "danger"),
    ("delete_records", {}, "danger"),
    ("commit_offsets", {}, "danger"),
    ("join_group", {}, "danger"),
    ("produce", {}, "danger"),
]

CLS_CASES = [
    ("describe_topics", {}, "allow"),
    ("describe_logsets", {}, "allow"),
    (
        "search_log",
        {"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z"},
        "allow",
    ),
    (
        "search_log",
        {"from": "2026-01-01T00:00:00Z"},
        "guard",
    ),
    (
        "search_log",
        {"from": "2026-01-02T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        "guard",
    ),
    (
        "search_log",
        {"from": "2026-01-01T00:00:00Z", "to": "2026-01-02T01:00:00Z"},
        "danger",
    ),
    ("upload_log", {}, "danger"),
    ("delete_topic", {}, "danger"),
    ("unknown_action", {}, "guard"),
]


@pytest.mark.parametrize(("action", "payload", "expected"), KAFKA_CASES)
def test_kafka_guard(action: str, payload: dict, expected: str) -> None:
    assert_decision(kafka_guard.check_kafka(action, payload), expected)


@pytest.mark.parametrize(("action", "payload", "expected"), CLS_CASES)
def test_cls_guard(action: str, payload: dict, expected: str) -> None:
    assert_decision(cls_guard.check_cls(action, payload), expected)


# ---------------------------------------------------------------------------
# require() 的错误码
# ---------------------------------------------------------------------------
def test_require_raises_with_guard_code() -> None:
    with pytest.raises(errors.GuardRejected) as excinfo:
        require(mysql_guard.check_sql("UPDATE orders SET status = 'x'"))

    assert excinfo.value.code == errors.GUARD_REJECTED


def test_require_raises_with_dangerous_code() -> None:
    with pytest.raises(errors.GuardRejected) as excinfo:
        require(redis_guard.check_redis("LRANGE", ["k", "0", "-1"]))

    assert excinfo.value.code == errors.DANGEROUS_OPERATION
