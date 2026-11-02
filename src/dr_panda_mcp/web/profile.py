"""我的页面：账号、MCP Token 管理、修改密码。"""

from __future__ import annotations

import asyncio
from datetime import UTC

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from dr_panda_mcp import auth
from dr_panda_mcp.config import Config
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import AuditEntry
from dr_panda_mcp.web import render


def _mcp_url(config: Config) -> str:
    if config.public_url:
        return config.public_url.rstrip("/") + "/mcp"
    host = config.host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{config.port}/mcp"


def _display_time(value) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def register_profile_routes(server: FastMCP, runtime: Runtime, config: Config) -> None:
    async def _current_profile():
        user = auth.current_user()
        if user is None:
            return None
        return await auth.get_profile(runtime.session_factory, user.id)

    def _render_me(
        request: Request,
        profile,
        *,
        error: str | None = None,
        password_error: str | None = None,
        token_error: str | None = None,
        new_token: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        response = render.render(
            "me.html",
            request=request,
            profile=profile,
            mcp_url=_mcp_url(config),
            token_prefix=profile.mcp_token_prefix,
            token_created=_display_time(profile.mcp_token_created_at),
            token_last_used=_display_time(profile.mcp_token_last_used_at),
            last_login=_display_time(profile.last_login_at),
            error=error,
            password_error=password_error,
            token_error=token_error,
            new_token=new_token,
            status_code=status_code,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @server.custom_route("/me", methods=["GET"])
    async def me_page(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        return _render_me(request, profile)

    @server.custom_route("/me/password", methods=["POST"])
    async def change_password(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        current = str(form.get("current_password", ""))
        new = str(form.get("new_password", ""))
        confirm = str(form.get("confirm_password", ""))
        verified = await auth.authenticate(
            runtime.session_factory, profile.user.username, current
        )
        if verified is None:
            return _render_me(request, profile, password_error="当前密码不正确", status_code=400)
        problem = auth.password_problem(new)
        if problem:
            return _render_me(request, profile, password_error=problem, status_code=400)
        if new != confirm:
            return _render_me(request, profile, password_error="两次输入的新密码不一致", status_code=400)
        if new == current:
            return _render_me(
                request, profile, password_error="新密码不能与当前密码相同", status_code=400
            )
        await auth.set_password(
            runtime.session_factory,
            profile.user.id,
            await asyncio.to_thread(auth.hash_password, new),
        )
        await runtime.store.append_audit(
            AuditEntry(
                actor=profile.user.username,
                action="user.password_change",
                summary="password changed; sessions invalidated",
            )
        )
        response = RedirectResponse("/login?flash=password_changed", status_code=303)
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        return response

    @server.custom_route("/me/mcp-token/rotate", methods=["POST"])
    async def rotate_token(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        current = str(form.get("current_password", ""))
        verified = await auth.authenticate(
            runtime.session_factory, profile.user.username, current
        )
        if verified is None:
            return _render_me(request, profile, token_error="当前密码不正确", status_code=400)
        token = auth.generate_token()
        await auth.rotate_mcp_token(
            runtime.session_factory,
            profile.user.id,
            token_hash=auth.hash_token(token),
            token_prefix=token[:12],
        )
        await runtime.store.append_audit(
            AuditEntry(
                actor=profile.user.username,
                action="user.mcp_token_rotate",
                summary=f"new token prefix={token[:12]}; old token invalidated",
            )
        )
        profile = await auth.get_profile(runtime.session_factory, profile.user.id)
        return _render_me(
            request,
            profile,
            new_token=token,
            status_code=200,
        )
