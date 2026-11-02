"""Jinja2 渲染（planning 4.4）：模板随包分发，开启自动转义。

统一注入主题、导航、版本与静态资源版本，页面无需各自处理。
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.requests import Request
from starlette.responses import HTMLResponse

from dr_panda_mcp import auth
from dr_panda_mcp.web import assets, i18n, theme

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)
_environment.globals["t"] = i18n.t
_environment.globals["plural"] = i18n.plural


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
            "current_user": auth.current_user(),
            "nav_active": (
                "me"
                if path.startswith("/me")
                else "settings"
                if path.startswith("/settings")
                else "targets"
            ),
            "app_version": _app_version(),
            "asset_version": assets.asset_version(),
            "script_version": assets.script_version(),
            "flash": flash,
        }
    )
    with i18n.use_locale(locale):
        body = _environment.get_template(template).render(**context)
    response = HTMLResponse(body, status_code=status_code)
    response.headers["Content-Language"] = locale
    response.headers["Vary"] = "Cookie"
    if request is not None and auth.CSRF_COOKIE not in request.cookies:
        response.set_cookie(
            auth.CSRF_COOKIE,
            csrf_token,
            max_age=12 * 3600,
            path="/",
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    return response
