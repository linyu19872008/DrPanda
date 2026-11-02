"""M7 HTTP 安全外壳：Web Session、MCP Bearer、CSRF。"""

from __future__ import annotations

import hmac
import logging
import time
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from dr_panda_mcp import auth
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.runtime import Runtime

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {"/healthz", "/login", "/favicon.ico"}
PUBLIC_PREFIXES = ("/static/",)


class AuthMiddleware:
    """在 FastMCP 之前校验 Web Session 或 /mcp Bearer。"""

    def __init__(
        self,
        app,
        *,
        runtime: Runtime,
        session_key: bytes,
        auth_required: bool = True,
    ) -> None:
        self.app = app
        self.runtime = runtime
        self.session_key = session_key
        self.auth_required = auth_required

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self.auth_required:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return

        if path == "/mcp" or path.startswith("/mcp/"):
            user = await self._bearer_user(request)
            if user is None:
                await _unauthorized()(scope, receive, send)
                return
            with auth.use_actor(user.username, user):
                await self.app(scope, receive, send)
            return

        session = await self._session_user(request)
        if session is None:
            target = request.url.path
            if request.url.query:
                target += "?" + request.url.query
            response = RedirectResponse(
                "/login?next=" + _quote(target), status_code=303
            )
            _clear_session(response)
            await response(scope, receive, send)
            return

        user, _payload = session
        with auth.use_actor(user.username, user):
            await self.app(scope, receive, send)

    async def _bearer_user(self, request: Request):
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        principal = await auth.authenticate_mcp_token(
            self.runtime.session_factory, auth.hash_token(token.strip())
        )
        if principal is None:
            return None
        try:
            await auth.touch_mcp_token_used(
                self.runtime.session_factory, principal.token_id
            )
        except Exception:  # 元数据更新失败不影响已认证的工具调用
            logger.warning("更新 MCP Token 最近使用时间失败", exc_info=True)
        return principal.user

    async def _session_user(self, request: Request):
        raw = request.cookies.get(auth.SESSION_COOKIE)
        if not raw:
            return None
        payload = auth.verify_session(raw, self.session_key)
        if payload is None:
            return None
        try:
            user_id = int(payload["uid"])
            auth_version = int(payload["av"])
        except (KeyError, TypeError, ValueError):
            return None
        user = await auth.get_user_by_id(self.runtime.session_factory, user_id)
        if user is None or not user.is_enabled or user.role != "admin":
            return None
        if user.auth_version != auth_version:
            return None
        try:
            current = await settings_module.load(self.runtime.store)
            ttl_seconds = current.session_ttl_minutes * 60
            issued = int(payload["iat"])
        except Exception:
            logger.warning("读取 Session 有效期失败", exc_info=True)
            return None
        if issued + ttl_seconds < int(time.time()):
            return None
        return user, payload


class CSRFMiddleware:
    """双提交 Cookie：所有普通 Web POST 必须带 _csrf。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        if (
            request.method != "POST"
            or request.url.path.startswith("/mcp")
            or request.url.path == "/login"
        ):
            await self.app(scope, receive, send)
            return
        cookie = request.cookies.get(auth.CSRF_COOKIE, "")
        body, replay = await _read_body(receive)
        form = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        token = (form.get("_csrf") or [""])[0]
        if not cookie or not token or not hmac.compare_digest(cookie, token):
            response = JSONResponse({"error": "csrf_failed"}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, replay, send)


async def _read_body(receive):
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    body = b"".join(chunks)
    sent = False

    async def replay():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return body, replay


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _clear_session(response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="dr-panda-mcp"'},
    )
