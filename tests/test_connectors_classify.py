from __future__ import annotations

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import classify
from dr_panda_mcp.tools.base import code_for


class _MySQLError(Exception):
    def __init__(self, errno: int, message: str = "boom", sqlstate: str = "") -> None:
        super().__init__(errno, message)
        self.sqlstate = sqlstate


def test_mysql_error_kinds() -> None:
    cases = {
        1054: errors.UpstreamQueryError,
        1064: errors.UpstreamQueryError,
        1146: errors.UpstreamQueryError,
        1045: errors.UpstreamAuthError,
        1044: errors.UpstreamAuthError,
        2003: errors.UpstreamUnavailable,
        1205: errors.UpstreamTimeout,
    }
    for errno, expected in cases.items():
        caught = classify.mysql_error(_MySQLError(errno), "mysql query failed")
        assert isinstance(caught, expected), errno
        assert str(caught).startswith("mysql query failed: ")


def test_mysql_sqlstate_fallback() -> None:
    exc = _MySQLError(0, "bad", sqlstate="42S22")
    assert isinstance(
        classify.mysql_error(exc, "mysql query failed"), errors.UpstreamQueryError
    )
    exc = _MySQLError(0, "denied", sqlstate="28000")
    assert isinstance(
        classify.mysql_error(exc, "mysql query failed"), errors.UpstreamAuthError
    )


class _MongoOperationError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"mongo error {code}")
        self.code = code


class ServerSelectionTimeoutError(Exception):
    pass


def test_mongo_error_kinds() -> None:
    assert isinstance(
        classify.mongo_error(_MongoOperationError(13), "mongo find 失败"),
        errors.UpstreamAuthError,
    )
    assert isinstance(
        classify.mongo_error(_MongoOperationError(2), "mongo find 失败"),
        errors.UpstreamQueryError,
    )
    assert isinstance(
        classify.mongo_error(_MongoOperationError(50), "mongo find 失败"),
        errors.UpstreamTimeout,
    )
    assert isinstance(
        classify.mongo_error(ServerSelectionTimeoutError("no host"), "mongo 探测失败"),
        errors.UpstreamUnavailable,
    )


class AuthenticationError(Exception):
    pass


class ResponseError(Exception):
    pass


class ConnectionError(Exception):
    pass


class TimeoutError(Exception):
    pass


def test_redis_error_kinds() -> None:
    assert isinstance(
        classify.redis_error(
            ResponseError("WRONGTYPE Operation against a key"), "redis 读取失败"
        ),
        errors.UpstreamQueryError,
    )
    assert isinstance(
        classify.redis_error(
            ResponseError("NOAUTH Authentication required."), "redis 读取失败"
        ),
        errors.UpstreamAuthError,
    )
    assert isinstance(
        classify.redis_error(AuthenticationError("bad password"), "redis 读取失败"),
        errors.UpstreamAuthError,
    )
    assert isinstance(
        classify.redis_error(ConnectionError("refused"), "redis 读取失败"),
        errors.UpstreamUnavailable,
    )
    assert isinstance(
        classify.redis_error(TimeoutError("slow"), "redis 读取失败"),
        errors.UpstreamTimeout,
    )


def test_es_http_status_mapping() -> None:
    assert isinstance(
        classify.es_http_error(400, "es 返回 HTTP 400"), errors.UpstreamQueryError
    )
    assert isinstance(
        classify.es_http_error(401, "es 返回 HTTP 401"), errors.UpstreamAuthError
    )
    assert isinstance(
        classify.es_http_error(403, "es 返回 HTTP 403"), errors.UpstreamAuthError
    )
    assert isinstance(
        classify.es_http_error(500, "es 返回 HTTP 500"), errors.UpstreamUnavailable
    )
    assert isinstance(
        classify.es_http_error(429, "es 返回 HTTP 429"), errors.UpstreamUnavailable
    )


def test_code_for_knows_the_new_codes() -> None:
    assert code_for(errors.UpstreamQueryError("x")) == errors.UPSTREAM_QUERY_ERROR
    assert code_for(errors.UpstreamAuthError("x")) == errors.UPSTREAM_AUTH
