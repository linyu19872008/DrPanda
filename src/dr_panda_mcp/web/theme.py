"""明暗主题：Cookie 三态 + 系统媒体查询（planning 4.1 / 4.4）。

- 无 Cookie：不输出 ``data-theme``，由 CSS 的 ``prefers-color-scheme`` 跟随系统
- ``POST /theme`` 写入 ``light`` / ``dark`` Cookie；选"跟随系统"则清除
- 全程零 JS，页面渲染时就知道当前主题，不会闪烁
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import Response

COOKIE_NAME = "drpanda_theme"
MODES = ("system", "light", "dark")
COOKIE_MAX_AGE = 365 * 24 * 3600


def normalize_mode(value: str | None) -> str:
    return value if value in MODES else "system"


def current_mode(request: Request) -> str:
    mode = request.cookies.get(COOKIE_NAME)
    return mode if mode in ("light", "dark") else "system"


def data_theme(mode: str) -> str | None:
    return mode if mode in ("light", "dark") else None


def safe_next(candidate: str | None, fallback: str = "/") -> str:
    """只允许站内路径，避免开放重定向。"""
    value = (candidate or "").strip()
    if not value.startswith("/") or value.startswith("//"):
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return fallback
    return value


def apply_theme(response: Response, mode: str) -> Response:
    if mode in ("light", "dark"):
        response.set_cookie(
            COOKIE_NAME,
            mode,
            max_age=COOKIE_MAX_AGE,
            path="/",
            httponly=True,
            samesite="lax",
        )
    else:
        response.delete_cookie(COOKIE_NAME, path="/")
    return response
