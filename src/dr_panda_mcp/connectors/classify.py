"""上游异常分类：连接 / 超时 / 查询被拒 / 认证失败。

驱动都是可选依赖，这里不 import 驱动，按 errno、mongo error code、HTTP 状态码和
异常类名做鸭子类型判断，避免分类逻辑绑死某个客户端版本。
"""

from __future__ import annotations

from dr_panda_mcp import errors


def _to_error(kind: str, message: str) -> errors.DrPandaError:
    if kind == "auth":
        return errors.UpstreamAuthError(message)
    if kind == "query":
        return errors.UpstreamQueryError(message)
    if kind == "timeout":
        return errors.UpstreamTimeout(message)
    return errors.UpstreamUnavailable(message)


def _first_int(exc: BaseException) -> int | None:
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int):
        return int(args[0])
    return None


# --- MySQL（asyncmy / pymysql 的 errno 与 SQLSTATE） ---

_MYSQL_UNAVAILABLE = {2002, 2003, 2005, 2006, 2013, 2026, 2055, 1040, 1053, 1129, 1130}
_MYSQL_AUTH = {1044, 1045, 1698, 1251, 1524, 1142, 1143}
_MYSQL_TIMEOUT = {1205, 1213, 1317}
_MYSQL_QUERY = {
    1049,
    1051,
    1052,
    1054,
    1055,
    1064,
    1065,
    1066,
    1109,
    1110,
    1113,
    1120,
    1136,
    1138,
    1146,
    1149,
    1235,
    1241,
    1242,
    1243,
    1248,
    1286,
    1292,
    1305,
    1630,
    1690,
}


def mysql_kind(exc: BaseException) -> str:
    errno = _first_int(exc)
    if errno in _MYSQL_TIMEOUT:
        return "timeout"
    if errno in _MYSQL_QUERY:
        return "query"
    if errno in _MYSQL_AUTH:
        return "auth"
    if errno in _MYSQL_UNAVAILABLE:
        return "unavailable"
    sqlstate = str(getattr(exc, "sqlstate", "") or "")
    if sqlstate.startswith("42"):
        return "query"
    if sqlstate.startswith("28"):
        return "auth"
    if sqlstate.startswith("08"):
        return "unavailable"
    if sqlstate.startswith("40"):
        return "timeout"
    return "unavailable"


def mysql_error(exc: BaseException, label: str) -> errors.DrPandaError:
    return _to_error(mysql_kind(exc), f"{label}：{exc}")


# --- Mongo（pymongo / motor 的 error code 与异常类名） ---

_MONGO_AUTH = {13, 18, 8000}
_MONGO_QUERY = {2, 9, 14, 20, 27, 72, 73, 121, 168, 10003, 11600, 17287}
_MONGO_TIMEOUT = {7, 50, 89, 262}
_MONGO_UNAVAILABLE = {6, 91, 112, 189, 9001, 10107, 13435, 13436}


def mongo_kind(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        if code in _MONGO_AUTH:
            return "auth"
        if code in _MONGO_TIMEOUT:
            return "timeout"
        if code in _MONGO_QUERY:
            return "query"
        if code in _MONGO_UNAVAILABLE:
            return "unavailable"
    name = type(exc).__name__
    if name in {
        "ServerSelectionTimeoutError",
        "ConnectionFailure",
        "AutoReconnect",
        "NetworkTimeout",
    }:
        return "unavailable"
    if "Timeout" in name:
        return "timeout"
    return "unavailable"


def mongo_error(exc: BaseException, label: str) -> errors.DrPandaError:
    return _to_error(mongo_kind(exc), f"{label}：{exc}")


# --- Elasticsearch（HTTP 状态码） ---


def es_http_error(status_code: int, message: str) -> errors.DrPandaError:
    if status_code in {401, 403}:
        return errors.UpstreamAuthError(message)
    if status_code in {400, 422}:
        return errors.UpstreamQueryError(message)
    return errors.UpstreamUnavailable(message)


# --- Redis（redis-py 异常类名与错误前缀） ---


def redis_kind(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc)
    if name in {"AuthenticationError", "NoPermissionError", "AuthorizationError"}:
        return "auth"
    if text.startswith(("NOAUTH", "WRONGPASS", "NOPERM")):
        return "auth"
    if name in {"TimeoutError", "SocketTimeoutError"} or "Timeout" in name:
        return "timeout"
    if name in {"ConnectionError", "BusyLoadingError", "ConnectionClosedError"}:
        return "unavailable"
    if name in {"ResponseError", "DataError", "ExecAbortError"}:
        return "query"
    return "unavailable"


def redis_error(exc: BaseException, label: str) -> errors.DrPandaError:
    return _to_error(redis_kind(exc), f"{label}：{exc}")
