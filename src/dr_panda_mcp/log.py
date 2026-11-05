"""进程日志：一行一个事件，带请求号，不写密钥和连接串。"""

from __future__ import annotations

import logging
import re
import secrets
import sys
import time
import traceback
from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders

from dr_panda_mcp import auth
from dr_panda_mcp.errors import (
    INTERNAL,
    STORAGE_UNAVAILABLE,
    UPSTREAM_NOT_FOUND,
    UPSTREAM_TIMEOUT,
    UPSTREAM_UNAVAILABLE,
)
from dr_panda_mcp.masking import redact

logger = logging.getLogger(__name__)

_REQUEST_ID: ContextVar[str] = ContextVar("dr_panda_request_id", default="")
_FIELDS = ("request", "actor", "tool", "env", "target", "elapsed_ms", "returned", "error")
_UPSTREAM = frozenset({UPSTREAM_TIMEOUT, UPSTREAM_UNAVAILABLE, UPSTREAM_NOT_FOUND})
_QUIET_PREFIXES = ("/static/",)
_QUIET_PATHS = frozenset({"/healthz", "/favicon.ico"})
_USERINFO = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@]+):[^/\s@]+@")


def configure_logging(level: str) -> None:
    """标准输出，一行一条。uvicorn 的访问日志改由本模块的 http 事件承担。"""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def database_kind(url: str) -> str:
    """只返回 sqlite、mysql 或 postgres，不带回主机和口令。"""
    scheme = urlsplit(url or "").scheme.split("+", 1)[0].lower()
    if scheme == "postgresql":
        return "postgres"
    if scheme in {"sqlite", "mysql", "postgres"}:
        return scheme
    return "unknown"


def current_request_id() -> str:
    return _REQUEST_ID.get()


def format_event(event: str, message: str = "", **fields: object) -> str:
    """拼一行事件。空字段省掉，说明里的换行压成空格。"""
    parts = [event]
    for key in _FIELDS:
        if key not in fields:
            continue
        text = _field(fields[key])
        if text:
            parts.append(f"{key}={text}")
    detail = _one_line(message)
    if detail:
        parts.append(detail)
    return " ".join(parts)


def log_tool_call(
    *,
    tool: str,
    target_name: str,
    environment_key: str | None,
    returned: int,
    started: float,
    error_code: str | None,
    error_message: str = "",
    secrets: list[str] | None = None,
    debug_hint: str = "",
) -> None:
    """一次工具调用只记一行。预期失败不带堆栈，未预期的失败带脱敏后的堆栈。"""
    hidden = secrets or []
    fields: dict[str, object] = {
        "request": current_request_id(),
        "actor": _actor(),
        "tool": tool,
        "env": environment_key or "",
        "target": target_name or "",
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "returned": returned,
        "error": error_code or "-",
    }
    if not error_code:
        logger.info(format_event("tool.call", **fields))
        _debug("tool.call", fields, debug_hint)
        return
    reason = _clip(_scrub(error_message or "", hidden), 200)
    if error_code == INTERNAL:
        line = format_event("tool.call", reason or "工具执行失败", **fields)
        stack = _redacted_traceback(hidden)
        if stack:
            logger.error("%s\n%s", line, stack)
        else:
            logger.error("%s", line)
        _debug("tool.call", fields, debug_hint)
        return
    event = "tool.call"
    if error_code in _UPSTREAM:
        event = "upstream.error"
    elif error_code == STORAGE_UNAVAILABLE:
        event = "store.error"
    logger.warning(format_event(event, reason, **fields))
    _debug(event, fields, debug_hint)


class RequestLogMiddleware:
    """给每个 HTTP 请求一个请求号，并在结束时记一行 http 事件。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = secrets.token_hex(4)
        token = _REQUEST_ID.set(request_id)
        started = time.perf_counter()
        status = 500
        path = scope.get("path") or "/"
        method = scope.get("method") or "-"

        async def send_with_id(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            line = format_event(
                "http",
                "未处理的异常",
                request=request_id,
                actor=_scope_actor(scope),
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            stack = _redacted_traceback([])
            if stack:
                logger.error("%s\n%s", line, stack)
            else:
                logger.error("%s", line)
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            level = _http_level(path, status)
            logger.log(
                level,
                format_event(
                    "http",
                    f"{method} {path} {status}",
                    request=request_id,
                    actor=_scope_actor(scope),
                    elapsed_ms=elapsed_ms,
                ),
            )
            _REQUEST_ID.reset(token)


def _debug(event: str, fields: dict[str, object], hint: str) -> None:
    if hint and logger.isEnabledFor(logging.DEBUG):
        logger.debug(format_event(event, hint, **fields))


def _http_level(path: str, status: int) -> int:
    if status >= 500:
        return logging.WARNING
    if status >= 400:
        return logging.INFO
    if path in _QUIET_PATHS or path.startswith(_QUIET_PREFIXES):
        return logging.DEBUG
    return logging.INFO


def _scope_actor(scope) -> str:
    state = scope.get("state")
    if not isinstance(state, dict):
        return ""
    actor = state.get("actor") or ""
    return actor if actor and actor != "anonymous" else ""


def _actor() -> str:
    actor = auth.current_actor()
    return "" if not actor or actor == "anonymous" else actor


def _field(value: object) -> str:
    text = str(value).strip()
    if not text or any(char.isspace() for char in text):
        return ""
    return text


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    chunk = text[:limit]
    space = chunk.rfind(" ")
    if space > limit // 2:
        return chunk[:space]
    return chunk


def failure_text(event: str, message: str = "", **fields: object) -> str:
    """预期失败的一行；若当前有异常，附上脱敏后的堆栈。"""
    line = format_event(event, message, **fields)
    stack = _redacted_traceback([])
    if not stack:
        return line
    return f"{line}\n{stack}"


def _scrub(text: str, secrets: list[str]) -> str:
    return _USERINFO.sub(r"\1:***@", redact(text, secrets))


def _redacted_traceback(secrets: list[str]) -> str:
    current = sys.exc_info()
    if current[0] is None:
        return ""
    text = "".join(traceback.format_exception(*current))
    return _scrub(text, secrets).rstrip()
