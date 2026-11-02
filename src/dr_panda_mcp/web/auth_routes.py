"""登录、登出路由（M7）。"""

from __future__ import annotations

import hmac
import time

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from dr_panda_mcp import auth
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.web import render, theme

_FAILED_LOGINS: dict[str, list[float]] = {}
_LOGIN_WINDOW = 300
_LOGIN_LIMIT = 5


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_limited(request: Request) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _FAILED_LOGINS.get(_client_key(request), []) if now - stamp < _LOGIN_WINDOW]
    _FAILED_LOGINS[_client_key(request)] = recent
    return len(recent) >= _LOGIN_LIMIT


def _record_login_failure(request: Request) -> None:
    _FAILED_LOGINS.setdefault(_client_key(request), []).append(time.monotonic())


def _clear_login_failures(request: Request) -> None:
    _FAILED_LOGINS.pop(_client_key(request), None)


def register_auth_routes(
    server: FastMCP,
    runtime: Runtime,
    session_key: bytes,
    *,
    secure_cookies: bool = False,
) -> None:
    @server.custom_route("/login", methods=["GET"])
    async def login_page(request: Request) -> HTMLResponse:
        notice = (
            "密码已修改，请重新登录"
            if request.query_params.get("flash") == "password_changed"
            else None
        )
        return render.render(
            "login.html",
            request=request,
            error=None,
            notice=notice,
            next_path=theme.safe_next(request.query_params.get("next", "/")),
        )

    @server.custom_route("/login", methods=["POST"])
    async def login_submit(request: Request) -> Response:
        form = await request.form()
        cookie = request.cookies.get(auth.CSRF_COOKIE, "")
        token = str(form.get("_csrf", ""))
        next_path = theme.safe_next(str(form.get("next", "/")))
        if not cookie or not token or not hmac.compare_digest(cookie, token):
            return render.render(
                "login.html",
                request=request,
                error="请求已过期，请重试",
                notice=None,
                next_path=next_path,
                status_code=403,
            )

        if _login_limited(request):
            return render.render(
                "login.html",
                request=request,
                error="登录尝试次数过多，请稍后再试",
                notice=None,
                next_path=next_path,
                status_code=429,
            )

        username = str(form.get("username", "admin")).strip() or "admin"
        password = str(form.get("password", ""))
        user = await auth.authenticate(runtime.session_factory, username, password)
        if user is None:
            _record_login_failure(request)
            return render.render(
                "login.html",
                request=request,
                error="用户名或密码错误",
                notice=None,
                next_path=next_path,
                status_code=401,
            )

        _clear_login_failures(request)
        current = await settings_module.load(runtime.store)
        session = auth.create_session(user, session_key, current.session_ttl_minutes * 60)
        await auth.set_last_login(runtime.session_factory, user.id)
        response = RedirectResponse(next_path, status_code=303)
        response.set_cookie(
            auth.SESSION_COOKIE,
            session,
            max_age=current.session_ttl_minutes * 60,
            path="/",
            httponly=True,
            samesite="lax",
            secure=secure_cookies or request.url.scheme == "https",
        )
        return response

    @server.custom_route("/logout", methods=["POST"])
    async def logout(request: Request) -> Response:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        return response
