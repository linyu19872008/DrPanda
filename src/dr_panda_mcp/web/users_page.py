"""管理员维护分析员账号。初始密码只在创建或重置后显示一次。"""

from __future__ import annotations

import asyncio
import time

from fastmcp import FastMCP
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from dr_panda_mcp import auth
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import AuditEntry
from dr_panda_mcp.web import async_api, render

_HELD: dict[str, tuple[float, int, str, str, str]] = {}
_HOLD_SECONDS = 120
_FLASH = {
    "disabled": "分析员已停用",
    "enabled": "分析员已启用",
}


def register_user_routes(server: FastMCP, runtime: Runtime) -> None:
    @server.custom_route("/users", methods=["GET"])
    async def users_page(request: Request) -> HTMLResponse:
        ticket = request.query_params.get("ticket", "")
        issued = _take(ticket) if ticket else None
        response = await _render_users(
            request,
            runtime,
            form_error=None,
            username="",
            flash=_flash(request),
            issued=issued,
            secret_gone=bool(ticket) and issued is None,
            create_open=request.query_params.get("new") == "1",
        )
        return response

    @server.custom_route("/users", methods=["POST"])
    async def create_user(request: Request) -> Response:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        typed = str(form.get("password", ""))
        problem = auth.username_problem(username)
        if problem is None and typed:
            problem = auth.password_problem(typed)
        if problem:
            return await _invalid(request, runtime, username, problem)
        existing = await auth.get_user_by_username(runtime.session_factory, username)
        if existing is not None:
            return await _invalid(request, runtime, username, "登录名已存在")
        password = typed or auth.generate_initial_password()
        try:
            created = await auth.create_analyst(
                runtime.session_factory,
                username=username,
                password_hash=await asyncio.to_thread(auth.hash_password, password),
            )
        except IntegrityError:
            return await _invalid(request, runtime, username, "登录名已存在")
        await runtime.store.append_audit(
            AuditEntry(
                actor=auth.current_actor(),
                action="user.create",
                target_name=created.username,
                summary=f"username={created.username}; role={created.role}",
            )
        )
        ticket = _issue(created.id, created.username, password, "created")
        location = f"/users?ticket={ticket}"
        if async_api.wants_json(request):
            return async_api.ok(request, data={"redirect": location})
        return RedirectResponse(location, status_code=303)

    @server.custom_route("/users/{user_id:int}/disable", methods=["POST"])
    async def disable_user(request: Request) -> Response:
        return await _set_enabled(request, runtime, False)

    @server.custom_route("/users/{user_id:int}/enable", methods=["POST"])
    async def enable_user(request: Request) -> Response:
        return await _set_enabled(request, runtime, True)

    @server.custom_route("/users/{user_id:int}/reset-password", methods=["POST"])
    async def reset_password(request: Request) -> Response:
        target = await auth.get_user_by_id(runtime.session_factory, request.path_params["user_id"])
        actor = auth.current_user()
        if (
            target is None
            or target.role != auth.ROLE_ANALYST
            or (actor is not None and actor.id == target.id)
        ):
            return RedirectResponse("/users", status_code=303)
        password = auth.generate_initial_password()
        await auth.set_password(
            runtime.session_factory,
            target.id,
            await asyncio.to_thread(auth.hash_password, password),
            must_change_password=True,
        )
        await runtime.store.append_audit(
            AuditEntry(
                actor=auth.current_actor(),
                action="user.password_reset",
                target_name=target.username,
                summary=f"username={target.username}",
            )
        )
        ticket = _issue(target.id, target.username, password, "reset")
        location = f"/users?ticket={ticket}"
        if async_api.wants_json(request):
            return async_api.ok(request, data={"redirect": location})
        return RedirectResponse(location, status_code=303)


async def _set_enabled(request: Request, runtime: Runtime, enabled: bool) -> Response:
    updated = await auth.set_user_enabled(
        runtime.session_factory, request.path_params["user_id"], enabled
    )
    if updated is not None:
        await runtime.store.append_audit(
            AuditEntry(
                actor=auth.current_actor(),
                action="user.enable" if enabled else "user.disable",
                target_name=updated.username,
                summary=f"username={updated.username}",
            )
        )
    if async_api.wants_json(request):
        if updated is None:
            return async_api.fail(request, async_api.CODE_BAD_REQUEST, "不能停用这个账号", status=400)
        return async_api.ok(
            request,
            data={
                "enabled": updated.is_enabled,
                "label": async_api.translate(
                    request, "已启用" if updated.is_enabled else "已停用"
                ),
            },
        )
    flash = "enabled" if enabled else "disabled"
    location = "/users" if updated is None else f"/users?flash={flash}"
    return RedirectResponse(location, status_code=303)


async def _render_users(
    request: Request,
    runtime: Runtime,
    *,
    form_error: str | None,
    username: str,
    flash: str | None,
    issued: tuple[str, str, str] | None = None,
    secret_gone: bool = False,
    create_open: bool = False,
    status_code: int = 200,
) -> HTMLResponse:
    accounts = await auth.list_managed_users(runtime.session_factory)
    response = render.render(
        "users.html",
        request=request,
        accounts=[_account_view(item) for item in accounts],
        form_error=form_error,
        username=username,
        flash=flash,
        issued_username=issued[0] if issued else "",
        issued_password=issued[1] if issued else "",
        issued_kind=issued[2] if issued else "",
        secret_gone=secret_gone,
        drawer_open=bool(form_error or issued or secret_gone or create_open),
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


async def _invalid(request: Request, runtime: Runtime, username: str, message: str) -> Response:
    if async_api.wants_json(request):
        return async_api.fail(request, async_api.CODE_INVALID_INPUT, message, status=400)
    return await _render_users(
        request,
        runtime,
        form_error=message,
        username=username,
        flash=None,
        status_code=400,
    )


def _account_view(item: auth.ManagedUser) -> dict:
    return {
        "id": item.id,
        "username": item.username,
        "role": item.role,
        "role_label": "管理员" if item.role == auth.ROLE_ADMIN else "分析员",
        "is_enabled": item.is_enabled,
        "last_login": item.last_login_at,
        "can_manage": item.role == auth.ROLE_ANALYST,
    }


def _flash(request: Request) -> str | None:
    return _FLASH.get(request.query_params.get("flash", ""))


def _issue(owner_id: int, username: str, password: str, kind: str) -> str:
    _purge()
    ticket = auth.new_csrf_token()
    _HELD[ticket] = (time.monotonic() + _HOLD_SECONDS, owner_id, username, password, kind)
    return ticket


def _take(ticket: str) -> tuple[str, str, str] | None:
    """一次性取出。票据只证明刚生成过，不把密码放进地址。"""
    if not ticket:
        return None
    item = _HELD.get(ticket)
    if item is None:
        return None
    expires, _owner, username, password, kind = item
    if expires < time.monotonic():
        _HELD.pop(ticket, None)
        return None
    user = auth.current_user()
    if user is not None and user.role != auth.ROLE_ADMIN:
        return None
    _HELD.pop(ticket, None)
    return username, password, kind


def _purge() -> None:
    now = time.monotonic()
    stale = [key for key, item in _HELD.items() if item[0] < now]
    for key in stale:
        _HELD.pop(key, None)
