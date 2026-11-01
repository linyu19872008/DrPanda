"""配置网页路由（planning 4.1–4.5）。

所有变更走 POST + 表单；Host/Origin 校验由 HTTP 中间件统一完成（3.5）。
"""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from dr_panda_mcp import errors as app_errors
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.connectors import get_connector
from dr_panda_mcp.masking import redact
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import ConfigStore, Target
from dr_panda_mcp.web import forms, render, views

logger = logging.getLogger(__name__)

ACTOR = "anonymous"


def register_web_routes(server: FastMCP, runtime: Runtime) -> None:
    store = runtime.store

    @server.custom_route("/", methods=["GET"])
    async def index(_: Request) -> HTMLResponse:
        targets = await store.list_all()
        return render.render(
            "index.html",
            groups=views.grouped(targets),
            type_options=forms.type_options(),
        )

    @server.custom_route("/targets/new", methods=["GET"])
    async def new_target(request: Request) -> Response:
        spec = forms.spec_for(request.query_params.get("type", ""))
        if spec is None:
            return _error("未知的目标类型", 400)
        values = forms.initial_values(spec)
        return _form_page(spec, values=values, errors={}, mode="create", existing=None)

    @server.custom_route("/targets", methods=["POST"])
    async def create_target(request: Request) -> Response:
        form = await request.form()
        spec = forms.spec_for(str(form.get("type", "")))
        if spec is None:
            return _error("未知的目标类型", 400)
        draft, errors, values = forms.parse_form(form, spec=spec, mode="create")
        if draft is None:
            return _form_page(
                spec, values=values, errors=errors, mode="create", existing=None, status=400
            )
        try:
            await store.create(draft, ACTOR)
        except app_errors.DrPandaError as exc:
            errors["_form"] = str(exc)
            return _form_page(
                spec, values=values, errors=errors, mode="create", existing=None, status=400
            )
        return RedirectResponse("/", status_code=303)

    @server.custom_route("/targets/{target_id:int}/edit", methods=["GET"])
    async def edit_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error("目标不存在", 404)
        return _edit_page(target, values=forms.initial_values(_spec(target), target), errors={})

    @server.custom_route("/targets/{target_id:int}", methods=["POST"])
    async def update_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error("目标不存在", 404)
        spec = _spec(target)
        form = await request.form()
        draft, errors, values = forms.parse_form(
            form, spec=spec, mode="edit", existing=target
        )
        if draft is None:
            return _edit_page(target, values=values, errors=errors, status=400)
        try:
            await store.update(target.id, draft, ACTOR)
        except app_errors.DrPandaError as exc:
            errors["_form"] = str(exc)
            return _edit_page(target, values=values, errors=errors, status=400)
        return RedirectResponse("/", status_code=303)

    @server.custom_route("/targets/{target_id:int}/toggle", methods=["POST"])
    async def toggle_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error("目标不存在", 404)
        await store.set_enabled(target.id, not target.enabled, ACTOR)
        return RedirectResponse("/", status_code=303)

    @server.custom_route("/targets/{target_id:int}/delete", methods=["GET"])
    async def delete_confirm(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error("目标不存在", 404)
        return render.render("delete.html", target=views.to_view(target))

    @server.custom_route("/targets/{target_id:int}/delete", methods=["POST"])
    async def delete_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error("目标不存在", 404)
        await store.delete(target.id, ACTOR)
        return RedirectResponse("/", status_code=303)

    @server.custom_route("/targets/{target_id:int}/test", methods=["POST"])
    async def test_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error("目标不存在", 404)
        ok = True
        message: str | None = None
        try:
            await runtime.catalog.test_connection(target.name, get_connector(target.type))
        except app_errors.DrPandaError as exc:
            ok = False
            message = redact(str(exc), target.secret.values())
        except Exception as exc:
            ok = False
            message = redact(f"未预期错误：{exc}", target.secret.values())
            logger.warning("测试连接失败：%s", target.name, exc_info=True)
        await store.record_test(target.id, ok, message, ACTOR)
        return RedirectResponse("/", status_code=303)

    @server.custom_route("/settings", methods=["GET"])
    async def settings_view(_: Request) -> HTMLResponse:
        current = await settings_module.load(store)
        return _settings_page(current, errors={})

    @server.custom_route("/settings", methods=["POST"])
    async def settings_save(request: Request) -> Response:
        form = await request.form()
        patch = {key: str(form.get(key, "")) for key in settings_module.DEFAULTS}
        try:
            await settings_module.update(store, patch, ACTOR)
        except app_errors.InvalidSettings as exc:
            current = await settings_module.load(store)
            return _settings_page(current, errors={"_form": str(exc)}, status=400)
        return RedirectResponse("/settings", status_code=303)


async def _target(store: ConfigStore, target_id: int) -> Target | None:
    return await store.get_by_id(target_id)


def _spec(target: Target) -> forms.TypeSpec:
    spec = forms.spec_for(target.type)
    if spec is None:  # pragma: no cover - 库里有未知类型属于数据损坏
        raise ValueError(f"数据库里存在未知类型 {target.type}")
    return spec


def _form_page(
    spec: forms.TypeSpec,
    *,
    values: dict[str, str],
    errors: dict[str, str],
    mode: str,
    existing: Target | None,
    status: int = 200,
) -> HTMLResponse:
    return render.render(
        "form.html",
        mode=mode,
        spec=spec,
        existing=existing,
        values=values,
        errors=errors,
        option_rows=forms.option_rows(spec, values, errors),
        secret_rows=forms.secret_rows(spec, errors, existing),
        common_rows=forms.common_rows(values, errors),
        status_code=status,
    )


def _edit_page(
    target: Target,
    *,
    values: dict[str, str],
    errors: dict[str, str],
    status: int = 200,
) -> HTMLResponse:
    spec = _spec(target)
    return _form_page(
        spec, values=values, errors=errors, mode="edit", existing=target, status=status
    )


def _settings_page(
    current: settings_module.Settings, *, errors: dict[str, str], status: int = 200
) -> HTMLResponse:
    rows = [
        {
            "key": key,
            "label": _SETTINGS_LABELS[key],
            "value": getattr(current, key),
            "default": default,
            "low": settings_module.RANGES[key][0],
            "high": settings_module.RANGES[key][1],
        }
        for key, default in settings_module.DEFAULTS.items()
    ]
    return render.render("settings.html", rows=rows, errors=errors, status_code=status)


def _error(message: str, status: int) -> Response:
    return PlainTextResponse(message, status_code=status)


_SETTINGS_LABELS = {
    "audit_retention_days": "审计保留天数",
    "target_max_concurrency": "每 target 并发上限",
}

__all__ = ["register_web_routes"]
