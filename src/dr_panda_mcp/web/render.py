"""Jinja2 渲染（planning 4.4）：模板随包分发，开启自动转义。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import HTMLResponse

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template: str, *, status_code: int = 200, **context: Any) -> HTMLResponse:
    return HTMLResponse(
        _environment.get_template(template).render(**context),
        status_code=status_code,
    )
