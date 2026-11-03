"""Jinja2 渲染（planning 4.4）：模板随包分发，开启自动转义。

统一注入主题、导航、版本与静态资源版本，页面无需各自处理。
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from dr_panda_mcp import auth
from dr_panda_mcp.web import assets, clock, i18n, theme

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
BRAND_NAME = "DrPanda"
PRODUCT_NAME = "DrPanda MCP"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)
_environment.globals["local_time"] = clock.local_time
_environment.globals["t"] = i18n.t
_environment.globals["plural"] = i18n.plural
_environment.globals["brand_name"] = BRAND_NAME
_environment.globals["product_name"] = PRODUCT_NAME


def _app_version() -> str:
    try:
        return version("dr-panda-mcp")
    except PackageNotFoundError:  # pragma: no cover - 源码直接运行时
        return "0.0.0"


def render(
    template: str,
    *,
    request: Request | None = None,
    status_code: int = 200,
    flash: dict[str, str] | None = None,
    **context: Any,
) -> HTMLResponse:
    mode = theme.current_mode(request) if request is not None else "system"
    path = request.url.path if request is not None else "/"
    query = request.url.query if request is not None else ""
    current_url = path + (f"?{query}" if query else "")
    locale = i18n.locale_from_request(request)
    csrf_token = request.cookies.get(auth.CSRF_COOKIE) if request is not None else None
    if not csrf_token:
        csrf_token = auth.new_csrf_token()
    current_user = auth.current_user()
    context.update(
        {
            "theme_mode": mode,
            "data_theme": theme.data_theme(mode),
            "current_path": path,
            "current_url": current_url,
            "locale": locale,
            "html_lang": locale,
            "language_options": i18n.language_options(),
            "csrf_token": csrf_token,
            "current_user": current_user,
            "is_admin": current_user is None or current_user.role == auth.ROLE_ADMIN,
            "show_nav": path != "/login",
            "nav_active": (
                "overview"
                if path == "/"
                else "me"
                if path.startswith("/me")
                else "settings"
                if path.startswith("/settings")
                else "users"
                if path.startswith("/users")
                else "audit"
                if path.startswith("/audit")
                else "environments"
                if path.startswith("/environments")
                else "targets"
                if path.startswith("/targets")
                else ""
            ),
            "app_version": _app_version(),
            "asset_version": assets.asset_version(),
            "script_version": assets.script_version(),
            "app_script_version": assets.app_js_version(),
            "icon_version": assets.icon_version(),
            "flash": flash,
        }
    )
    with i18n.use_locale(locale):
        body = _environment.get_template(template).render(**context)
    response = HTMLResponse(body, status_code=status_code)
    response.headers["Content-Language"] = locale
    response.headers["Vary"] = "Cookie"
    _slide_auth_cookies(request, response, csrf_token)
    return response


def _slide_auth_cookies(
    request: Request | None, response: Response, csrf_token: str | None
) -> None:
    """按当前 Session 时长续上 CSRF，并续上已经登录的会话 Cookie。"""
    if request is None:
        return
    ttl = int(getattr(request.state, "session_ttl_seconds", 720 * 60) or 720 * 60)
    secure = request.url.scheme == "https"
    csrf = request.cookies.get(auth.CSRF_COOKIE) or csrf_token
    if csrf:
        response.set_cookie(
            auth.CSRF_COOKIE,
            csrf,
            max_age=ttl,
            path="/",
            httponly=True,
            samesite="lax",
            secure=secure,
        )
    raw = getattr(request.state, "session_raw", None)
    if raw:
        response.set_cookie(
            auth.SESSION_COOKIE,
            raw,
            max_age=ttl,
            path="/",
            httponly=True,
            samesite="lax",
            secure=secure,
        )
