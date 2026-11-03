"""M7 HTTP 安全外壳：Web Session、MCP Bearer、CSRF。"""

from __future__ import annotations

import hmac
import logging
import time
from urllib.parse import parse_qs

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from dr_panda_mcp import auth
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.web import async_api, render

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {"/healthz", "/login", "/favicon.ico"}
PUBLIC_PREFIXES = ("/static/",)

# 全局安全响应头：模板没有内联脚本/样式，脚本与网络请求只允许同源。
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "object-src 'none'"
)
SECURITY_HEADERS = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
}


class SecurityHeadersMiddleware:
    """给所有响应补安全头（纯 ASGI，避免 BaseHTTPMiddleware 的流式问题）。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in SECURITY_HEADERS.items():
                    headers.setdefault(key, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class NotFoundMiddleware(BaseHTTPMiddleware):
    """把 FastMCP/Starlette 的未知 GET 路由替换为站内 404 页面。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            response.status_code == 404
            and request.method == "GET"
            and not path.startswith(("/mcp", "/static"))
        ):
            return render.render(
                "error.html",
                request=request,
                title="页面不存在",
                message="页面不存在",
                code=404,
                status_code=404,
            )
        return response


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
            principal = await self._bearer_user(request)
            if principal is None:
                await _unauthorized()(scope, receive, send)
                return
            with auth.use_actor(
                principal.user.username,
                principal.user,
                client=auth.ClientIdentity(
                    name=principal.token_name,
                    prefix=principal.token_prefix,
                ),
            ):
                await self.app(scope, receive, send)
            return

        session = await self._session_user(request)
        if session is None:
            target = request.url.path
            if request.url.query:
                target += "?" + request.url.query
            if async_api.wants_json(request):
                response = async_api.fail(
                    request,
                    async_api.CODE_UNAUTHORIZED,
                    "登录状态已失效，请重新登录",
                    status=401,
                    data={"login": "/login?next=" + _quote(target)},
                )
            else:
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
        return principal

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
        request.state.session_ttl_seconds = ttl_seconds
        request.state.session_raw = raw
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
            if async_api.wants_json(request):
                response = async_api.fail(
                    request,
                    async_api.CODE_CSRF_EXPIRED,
                    "页面已过期，请刷新后重试",
                    status=403,
                )
            else:
                response = render.render(
                    "error.html",
                    request=request,
                    title="请求已过期",
                    message="页面已过期，请刷新后重试",
                    code=403,
                    status_code=403,
                )
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
