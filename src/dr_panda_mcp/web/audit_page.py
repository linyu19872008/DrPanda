"""只读审计页：按时间、动作、环境和对象查看已经发生的操作。"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.web import render

PAGE_SIZE = 50
RANGES = (
    ("24h", "近 24 小时", timedelta(hours=24)),
    ("7d", "近 7 天", timedelta(days=7)),
    ("30d", "近 30 天", timedelta(days=30)),
)
ACTIONS = (
    ("environment.create", "新建环境"),
    ("environment.update", "修改环境"),
    ("environment.enable", "启用环境"),
    ("environment.disable", "停用环境"),
    ("environment.delete", "删除环境"),
    ("target.create", "新建目标"),
    ("target.update", "修改目标"),
    ("target.enable", "启用目标"),
    ("target.disable", "停用目标"),
    ("target.delete", "删除目标"),
    ("target.test", "测试连接"),
    ("tool.call", "工具调用"),
    ("settings.update", "修改配置"),
    ("user.mcp_token_create", "生成 Token"),
    ("user.mcp_token_delete", "删除 Token"),
    ("user.password_change", "修改密码"),
)
_ACTION_LABELS = dict(ACTIONS)
_RANGE_KEYS = {key: delta for key, _label, delta in RANGES}


def _clean(value: str, limit: int) -> str:
    return value.strip()[:limit]


def _href(
    *,
    range_key: str,
    action: str,
    env: str,
    q: str,
    page: int | None = None,
) -> str:
    params: list[tuple[str, str]] = []
    if range_key != "24h":
        params.append(("range", range_key))
    if action:
        params.append(("action", action))
    if env:
        params.append(("env", env))
    if q:
        params.append(("q", q))
    if page and page > 1:
        params.append(("page", str(page)))
    if not params:
        return "/audit"
    return "/audit?" + urlencode(params)


def register_audit_routes(server: FastMCP, runtime: Runtime) -> None:
    @server.custom_route("/audit", methods=["GET"])
    async def audit_page(request: Request) -> HTMLResponse:
        params = request.query_params
        range_key = params.get("range", "24h")
        if range_key not in _RANGE_KEYS:
            range_key = "24h"
        action = _clean(params.get("action", ""), 32)
        if action not in _ACTION_LABELS:
            action = ""
        env = _clean(params.get("env", ""), 64)
        q = _clean(params.get("q", ""), 64)
        try:
            page = int(params.get("page", "1"))
        except ValueError:
            page = 1
        page = max(page, 1)
        since = datetime.now(UTC) - _RANGE_KEYS[range_key]
        rows, total = await runtime.store.list_audit(
            since=since,
            action=action or None,
            environment_key=env or None,
            target_name=q or None,
            offset=(page - 1) * PAGE_SIZE,
            limit=PAGE_SIZE,
        )
        pages = max(1, math.ceil(total / PAGE_SIZE))
        if page > pages:
            page = pages
            rows, total = await runtime.store.list_audit(
                since=since,
                action=action or None,
                environment_key=env or None,
                target_name=q or None,
                offset=(page - 1) * PAGE_SIZE,
                limit=PAGE_SIZE,
            )
        environments = await runtime.store.list_environments()
        titles = {item.key: item.title for item in environments}
        view_rows = [
            {
                "at": row.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                "actor": row.actor,
                "action_label": _ACTION_LABELS.get(row.action, row.action),
                "environment_key": row.environment_key,
                "environment_title": titles.get(row.environment_key or ""),
                "target_name": row.target_name,
                "summary": row.summary or "",
            }
            for row in rows
        ]
        filtered = range_key != "24h" or bool(action or env or q)
        response = render.render(
            "audit.html",
            request=request,
            rows=view_rows,
            total=total,
            page=page,
            pages=pages,
            range_key=range_key,
            ranges=[
                {
                    "key": key,
                    "label": label,
                    "active": key == range_key,
                    "href": _href(range_key=key, action=action, env=env, q=q),
                }
                for key, label, _delta in RANGES
            ],
            actions=ACTIONS,
            action=action,
            environments=environments,
            env=env,
            q=q,
            filtered=filtered,
            prev_href=_href(range_key=range_key, action=action, env=env, q=q, page=page - 1),
            next_href=_href(range_key=range_key, action=action, env=env, q=q, page=page + 1),
        )
        response.headers["Cache-Control"] = "no-store"
        return response
