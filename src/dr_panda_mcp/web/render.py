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

from dr_panda_mcp.web import assets, theme

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)


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
    context.update(
        {
            "theme_mode": mode,
            "data_theme": theme.data_theme(mode),
            "current_path": path,
            "nav_active": "settings" if path.startswith("/settings") else "targets",
            "app_version": _app_version(),
            "asset_version": assets.asset_version(),
            "flash": flash,
        }
    )
    return HTMLResponse(
        _environment.get_template(template).render(**context),
        status_code=status_code,
    )
