"""我的页面：账号、MCP Token 管理、修改密码。"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from dr_panda_mcp import auth
from dr_panda_mcp.config import Config
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import AuditEntry
from dr_panda_mcp.web import async_api, render

PAGE_SIZE = 20


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

    async def _render_me_with_tokens(
        request: Request,
        profile,
        *,
        page: int = 1,
        error: str | None = None,
        password_error: str | None = None,
        modal_open: bool = False,
        modal_error: str | None = None,
        token_name: str = "",
        new_token: str | None = None,
        status_code: int = 200,
        notice: str | None = None,
    ) -> HTMLResponse:
        total = await auth.count_mcp_tokens(runtime.session_factory, profile.user.id)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        page = min(max(page, 1), pages)
        tokens = await auth.list_mcp_tokens(
            runtime.session_factory,
            profile.user.id,
            offset=(page - 1) * PAGE_SIZE,
            limit=PAGE_SIZE,
        )
        response = render.render(
            "me.html",
            request=request,
            profile=profile,
            mcp_url=_mcp_url(config),
            page=page,
            page_size=PAGE_SIZE,
            total=total,
            tokens=tokens,
            pages=pages,
            error=error,
            password_error=password_error,
            modal_open=modal_open,
            modal_error=modal_error,
            token_name=token_name,
            new_token=new_token,
            notice=notice,
            last_login=_display_time(profile.last_login_at),
            status_code=status_code,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @server.custom_route("/me", methods=["GET"])
    async def me_page(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError:
            page = 1
        notice = "Token 已删除" if request.query_params.get("deleted") == "1" else None
        return await _render_me_with_tokens(request, profile, page=page, notice=notice)

    @server.custom_route("/me/tokens/new", methods=["GET"])
    async def new_token_page(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        response = render.render("token_new.html", request=request, error=None)
        response.headers["Cache-Control"] = "no-store"
        return response

    @server.custom_route("/me/tokens", methods=["POST"])
    async def create_token(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        raw_name = str(form.get("name", "")).strip()
        name = raw_name or None
        if name is not None and len(name) > 64:
            return await _render_me_with_tokens(
                request,
                profile,
                modal_open=True,
                modal_error="Token 名称不能超过 64 个字符",
                token_name=raw_name,
                status_code=400,
            )
        if name is not None and await auth.mcp_token_name_exists(
            runtime.session_factory, profile.user.id, name
        ):
            return await _render_me_with_tokens(
                request,
                profile,
                modal_open=True,
                modal_error="Token 名称已存在，请换一个",
                token_name=name,
                status_code=400,
            )
        token = auth.generate_token()
        await auth.create_mcp_token(
            runtime.session_factory,
            profile.user.id,
            name=name,
            token_hash=auth.hash_token(token),
            token_prefix=token[:12],
        )
        await runtime.store.append_audit(
            AuditEntry(
                actor=profile.user.username,
                action="user.mcp_token_create",
                summary=f"name={name or '-'}; prefix={token[:12]}",
            )
        )
        response = await _render_me_with_tokens(
            request,
            profile,
            modal_open=True,
            token_name=name or "",
            new_token=token,
            status_code=200,
        )
        return response

    @server.custom_route("/me/tokens/{token_id:int}/delete", methods=["GET"])
    async def delete_token_page(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        token = await auth.get_mcp_token(
            runtime.session_factory, profile.user.id, request.path_params["token_id"]
        )
        if token is None:
            return await _render_me_with_tokens(request, profile, error="Token 不存在", status_code=404)
        response = render.render("token_delete.html", request=request, token=token)
        response.headers["Cache-Control"] = "no-store"
        return response

    @server.custom_route("/me/tokens/{token_id:int}/delete", methods=["POST"])
    async def delete_token(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        token = await auth.get_mcp_token(
            runtime.session_factory, profile.user.id, request.path_params["token_id"]
        )
        if token is None:
            return RedirectResponse("/me", status_code=303)
        deleted = await auth.delete_mcp_token(
            runtime.session_factory, profile.user.id, token.id
        )
        if deleted:
            await runtime.store.append_audit(
                AuditEntry(
                    actor=profile.user.username,
                    action="user.mcp_token_delete",
                    summary=f"name={token.name or '-'}; prefix={token.token_prefix or '-'}",
                )
            )
        return RedirectResponse("/me?deleted=1", status_code=303)

    @server.custom_route("/me/password", methods=["POST"])
    async def change_password(request: Request) -> Response:
        profile = await _current_profile()
        if profile is None:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()

        async def _error(message: str) -> Response:
            if async_api.wants_json(request):
                return async_api.fail(
                    request, async_api.CODE_INVALID_INPUT, message, status=400
                )
            return await _render_me_with_tokens(
                request, profile, password_error=message, status_code=400
            )

        current = str(form.get("current_password", ""))
        new = str(form.get("new_password", ""))
        confirm = str(form.get("confirm_password", ""))
        verified = await auth.authenticate(
            runtime.session_factory, profile.user.username, current
        )
        if verified is None:
            return await _error("当前密码不正确")
        problem = auth.password_problem(new)
        if problem:
            return await _error(problem)
        if new != confirm:
            return await _error("两次输入的新密码不一致")
        if new == current:
            return await _error("新密码不能与当前密码相同")
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
        if async_api.wants_json(request):
            response: Response = async_api.ok(
                request, data={"redirect": "/login?flash=password_changed"}
            )
        else:
            response = RedirectResponse("/login?flash=password_changed", status_code=303)
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        return response
