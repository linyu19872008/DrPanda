"""静态资源：手写 CSS，无构建链（planning 4.4）。

只暴露固定的 ``/static/app.css``，带 ETag 与短缓存；模板用 ``?v=<hash>`` 破缓存。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

STATIC_DIR = Path(__file__).resolve().parent / "static"
CSS_PATH = STATIC_DIR / "app.css"


def _read_css() -> bytes:
    return CSS_PATH.read_bytes()


def asset_version() -> str:
    return hashlib.sha256(_read_css()).hexdigest()[:10]


def css_response(request: Request) -> Response:
    data = _read_css()
    etag = f'"{hashlib.sha256(data).hexdigest()}"'
    headers = {"Cache-Control": "public, max-age=300", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(data, media_type="text/css; charset=utf-8", headers=headers)
