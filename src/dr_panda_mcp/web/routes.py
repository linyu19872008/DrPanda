"""配置网页路由（planning 4.1–4.5）。

所有变更走 POST + 表单；Host/Origin 校验由 HTTP 中间件统一完成（3.5）。
主题用 Cookie 三态实现，静态 CSS 由固定路由提供，全程不写 JS。
"""

from __future__ import annotations

import logging
from collections import Counter
from urllib.parse import urlencode

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from dr_panda_mcp import errors as app_errors
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.connectors import get_connector
from dr_panda_mcp.masking import redact
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import ConfigStore, Target
from dr_panda_mcp.web import assets, forms, render, theme, views

logger = logging.getLogger(__name__)

ACTOR = "anonymous"

_FLASH_MESSAGES = {
    "created": ("success", "目标已创建"),
    "updated": ("success", "修改已保存"),
    "toggled": ("success", "启用状态已切换"),
    "deleted": ("success", "目标已删除"),
    "saved": ("success", "系统配置已保存"),
}


def register_web_routes(server: FastMCP, runtime: Runtime) -> None:
    store = runtime.store

    @server.custom_route("/", methods=["GET"])
    async def index(request: Request) -> HTMLResponse:
        all_views = views.list_views(await store.list_all())
        q = request.query_params.get("q", "").strip()
        type_ = request.query_params.get("type", "").strip() or None
        if type_ is not None and type_ not in forms.TYPE_SPECS:
            type_ = None
        rows = views.filter_views(all_views, q=q, type_=type_)
        return render.render(
            "index.html",
            request=request,
            flash=_flash(request),
            rows=rows,
            stats=views.stats(all_views),
            q=q,
            active_type=type_,
            type_filters=_type_filters(q, type_, all_views),
            has_targets=bool(all_views),
        )

    @server.custom_route("/targets/new", methods=["GET"])
    async def new_target(request: Request) -> Response:
        type_ = request.query_params.get("type", "").strip()
        if not type_:
            return render.render(
                "targets_new.html",
                request=request,
                type_cards=forms.type_cards(),
            )
        spec = forms.spec_for(type_)
        if spec is None:
            return _error(request, "未知的目标类型", 400, "无法新建目标")
        values = forms.initial_values(spec)
        return _form_page(
            request, spec, values=values, errors={}, mode="create", existing=None
        )

    @server.custom_route("/targets", methods=["POST"])
    async def create_target(request: Request) -> Response:
        form = await request.form()
        spec = forms.spec_for(str(form.get("type", "")))
        if spec is None:
            return _error(request, "未知的目标类型", 400, "无法新建目标")
        draft, errors, values = forms.parse_form(form, spec=spec, mode="create")
        if draft is None:
            return _form_page(
                request,
                spec,
                values=values,
                errors=errors,
                mode="create",
                existing=None,
                status=400,
            )
        try:
            await store.create(draft, ACTOR)
        except app_errors.DrPandaError as exc:
            errors["_form"] = str(exc)
            return _form_page(
                request,
                spec,
                values=values,
                errors=errors,
                mode="create",
                existing=None,
                status=400,
            )
        return _redirect("/", flash="created")

    @server.custom_route("/targets/{target_id:int}/edit", methods=["GET"])
    async def edit_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error(request, "目标不存在或已被删除", 404, "找不到目标")
        return _edit_page(
            request, target, values=forms.initial_values(_spec(target), target), errors={}
        )

    @server.custom_route("/targets/{target_id:int}", methods=["POST"])
    async def update_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error(request, "目标不存在或已被删除", 404, "找不到目标")
        spec = _spec(target)
        form = await request.form()
        draft, errors, values = forms.parse_form(
            form, spec=spec, mode="edit", existing=target
        )
        if draft is None:
            return _edit_page(request, target, values=values, errors=errors, status=400)
        try:
            await store.update(target.id, draft, ACTOR)
        except app_errors.DrPandaError as exc:
            errors["_form"] = str(exc)
            return _edit_page(request, target, values=values, errors=errors, status=400)
        return _redirect("/", flash="updated")

    @server.custom_route("/targets/{target_id:int}/toggle", methods=["POST"])
    async def toggle_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error(request, "目标不存在或已被删除", 404, "找不到目标")
        await store.set_enabled(target.id, not target.enabled, ACTOR)
        return _redirect("/", flash="toggled")

    @server.custom_route("/targets/{target_id:int}/delete", methods=["GET"])
    async def delete_confirm(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error(request, "目标不存在或已被删除", 404, "找不到目标")
        return render.render(
            "delete.html", request=request, target=views.to_view(target)
        )

    @server.custom_route("/targets/{target_id:int}/delete", methods=["POST"])
    async def delete_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error(request, "目标不存在或已被删除", 404, "找不到目标")
        await store.delete(target.id, ACTOR)
        return _redirect("/", flash="deleted")

    @server.custom_route("/targets/{target_id:int}/test", methods=["POST"])
    async def test_target(request: Request) -> Response:
        target = await _target(store, request.path_params["target_id"])
        if target is None:
            return _error(request, "目标不存在或已被删除", 404, "找不到目标")
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
        return _redirect(
            "/", flash="tested", result="ok" if ok else "fail", name=target.name
        )

    @server.custom_route("/settings", methods=["GET"])
    async def settings_view(request: Request) -> HTMLResponse:
        current = await settings_module.load(store)
        return _settings_page(request, current, errors={}, flash=_flash(request))

    @server.custom_route("/settings", methods=["POST"])
    async def settings_save(request: Request) -> Response:
        form = await request.form()
        patch = {key: str(form.get(key, "")) for key in settings_module.DEFAULTS}
        try:
            await settings_module.update(store, patch, ACTOR)
        except app_errors.InvalidSettings as exc:
            current = await settings_module.load(store)
            return _settings_page(
                request, current, errors={"_form": str(exc)}, status=400
            )
        return _redirect("/settings", flash="saved")

    @server.custom_route("/theme", methods=["POST"])
    async def set_theme(request: Request) -> Response:
        form = await request.form()
        mode = theme.normalize_mode(str(form.get("mode", "system")))
        next_path = theme.safe_next(str(form.get("next", "/")))
        response = RedirectResponse(next_path, status_code=303)
        return theme.apply_theme(response, mode)

    @server.custom_route("/static/app.css", methods=["GET"])
    async def app_css(request: Request) -> Response:
        return assets.css_response(request)


async def _target(store: ConfigStore, target_id: int) -> Target | None:
    return await store.get_by_id(target_id)


def _spec(target: Target) -> forms.TypeSpec:
    spec = forms.spec_for(target.type)
    if spec is None:  # pragma: no cover - 库里有未知类型属于数据损坏
        raise ValueError(f"数据库里存在未知类型 {target.type}")
    return spec


def _type_filters(
    q: str, active_type: str | None, all_views: list[views.TargetView]
) -> list[dict]:
    counts = Counter(view.type for view in all_views)
    items = [
        {
            "type": "",
            "label": "全部",
            "count": len(all_views),
            "href": _list_href(q, None),
            "active": active_type is None,
        }
    ]
    for type_, spec in forms.TYPE_SPECS.items():
        items.append(
            {
                "type": type_,
                "label": spec.label,
                "count": counts.get(type_, 0),
                "href": _list_href(q, type_),
                "active": active_type == type_,
            }
        )
    return items


def _list_href(q: str, type_: str | None) -> str:
    params: dict[str, str] = {}
    if q:
        params["q"] = q
    if type_:
        params["type"] = type_
    return "/" + (f"?{urlencode(params)}" if params else "")


def _flash(request: Request) -> dict[str, str] | None:
    code = request.query_params.get("flash", "")
    if code == "tested":
        name = request.query_params.get("name", "")
        if request.query_params.get("result") == "ok":
            return {"tone": "success", "title": f"{name} 连接测试成功", "detail": ""}
        return {
            "tone": "danger",
            "title": f"{name} 连接测试失败",
            "detail": "失败原因已记录在目标行，可展开查看。",
        }
    message = _FLASH_MESSAGES.get(code)
    if message is None:
        return None
    tone, title = message
    return {"tone": tone, "title": title, "detail": ""}


def _redirect(path: str, **params: str) -> RedirectResponse:
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(path, status_code=303)


def _form_page(
    request: Request,
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
        request=request,
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
    request: Request,
    target: Target,
    *,
    values: dict[str, str],
    errors: dict[str, str],
    status: int = 200,
) -> HTMLResponse:
    spec = _spec(target)
    return _form_page(
        request,
        spec,
        values=values,
        errors=errors,
        mode="edit",
        existing=target,
        status=status,
    )


def _settings_page(
    request: Request,
    current: settings_module.Settings,
    *,
    errors: dict[str, str],
    flash: dict[str, str] | None = None,
    status: int = 200,
) -> HTMLResponse:
    rows = [
        {
            "key": key,
            "label": _SETTINGS_LABELS[key],
            "value": getattr(current, key),
            "default": default,
            "low": settings_module.RANGES[key][0],
            "high": settings_module.RANGES[key][1],
                "help": _SETTINGS_HELP[key],
            "unit": "天" if key == "audit_retention_days" else "个",
        }
        for key, default in settings_module.DEFAULTS.items()
    ]
    return render.render(
        "settings.html",
        request=request,
        rows=rows,
        errors=errors,
        flash=flash,
        status_code=status,
    )


def _error(
    request: Request, message: str, status: int, title: str | None = None
) -> HTMLResponse:
    return render.render(
        "error.html",
        request=request,
        message=message,
        code=status,
        status_code=status,
        title=title or ("页面不存在" if status == 404 else "请求有误"),
    )


_SETTINGS_LABELS = {
    "audit_retention_days": "审计保留天数",
    "target_max_concurrency": "每 target 并发上限",
}

_SETTINGS_HELP = {
    "audit_retention_days": "超过该天数的审计记录会被定时清理；清理只记日志。",
    "target_max_concurrency": "同一个目标同时进行的工具调用上限，超出会排队。",
}
