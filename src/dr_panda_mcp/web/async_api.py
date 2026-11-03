"""网页异步交互：JSON 双模式与统一错误信封（frontend-js-policy v2）。

同一组 POST 路由同时服务两种客户端：

- 普通表单（无 JS / JS 失败）：返回 303 重定向或服务端重渲染的 HTML；
- 同源 ``fetch``（渐进增强）：带 ``Accept: application/json``，返回统一 JSON。

服务端校验只有一份（CSRF、Host/Origin、权限、字段校验、探测闸门），
本模块只负责识别请求形态、翻译文案与构造响应，不承载业务判断。
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from dr_panda_mcp.web import i18n

JSON_HEADERS = {"Cache-Control": "no-store"}

# 错误码：前端按 code 决定动作，message 只用于展示。
CODE_INVALID_INPUT = "INVALID_INPUT"
CODE_PROBE_FAILED = "PROBE_FAILED"
CODE_PROBE_REQUIRED = "PROBE_REQUIRED"
CODE_CONFLICT = "CONFLICT"
CODE_CSRF_EXPIRED = "CSRF_EXPIRED"
CODE_UNAUTHORIZED = "UNAUTHORIZED"
CODE_AUTH_FAILED = "AUTH_FAILED"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_BAD_REQUEST = "BAD_REQUEST"
CODE_RATE_LIMITED = "RATE_LIMITED"
CODE_UNAVAILABLE = "UNAVAILABLE"


def wants_json(request: Request) -> bool:
    """同源 fetch 约定：带 ``Accept: application/json`` 即走 JSON 响应。"""
    accept = request.headers.get("accept", "")
    return "application/json" in accept.lower()


def translate(request: Request, source: str, **params: Any) -> str:
    """按请求语言翻译文案（JSON 响应没有模板里的 ``t()`` 包装）。"""
    with i18n.use_locale(i18n.locale_from_request(request)):
        return i18n.t(source, **params)


def _payload(
    ok: bool,
    *,
    code: str | None = None,
    message: str | None = None,
    errors: dict[str, str] | None = None,
    phase: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": ok}
    if code:
        payload["code"] = code
    if message:
        payload["message"] = message
    if errors:
        payload["errors"] = errors
    if phase:
        payload["phase"] = phase
    if data:
        payload.update(data)
    return payload


def ok(
    request: Request,
    *,
    status: int = 200,
    message: str | None = None,
    message_params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        _payload(
            True,
            message=(
                translate(request, message, **(message_params or {}))
                if message
                else None
            ),
            data=data,
        ),
        status_code=status,
        headers=JSON_HEADERS,
    )


def fail(
    request: Request,
    code: str,
    message: str,
    *,
    status: int = 400,
    message_params: dict[str, Any] | None = None,
    errors: dict[str, str] | None = None,
    phase: str | None = None,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    translated_errors = (
        {key: translate(request, value) for key, value in errors.items()}
        if errors
        else None
    )
    return JSONResponse(
        _payload(
            False,
            code=code,
            message=translate(request, message, **(message_params or {})),
            errors=translated_errors,
            phase=phase,
            data=data,
        ),
        status_code=status,
        headers=JSON_HEADERS,
    )


def invalid_input(
    request: Request,
    errors: dict[str, str],
    *,
    count: int | None = None,
) -> JSONResponse:
    total = count if count is not None else len(errors)
    return fail(
        request,
        CODE_INVALID_INPUT,
        "有 {count} 处需要修改",
        status=400,
        message_params={"count": total},
        errors=errors,
        data={"count": total},
    )
