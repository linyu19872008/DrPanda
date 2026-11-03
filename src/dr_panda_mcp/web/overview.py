"""首页概览。管理员看全局健康，分析员只看自己能用的数量和调用。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse

from dr_panda_mcp import auth
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.web import render, views
from dr_panda_mcp.web.audit_page import action_label, describe_summary

_AUDIT_FLOOR = datetime(2000, 1, 1, tzinfo=UTC)
_ATTENTION_LIMIT = 5
_RECENT_LIMIT = 5


def register_overview_routes(server: FastMCP, runtime: Runtime) -> None:
    @server.custom_route("/", methods=["GET"])
    async def overview(request: Request) -> HTMLResponse:
        user = auth.current_user()
        is_admin = user is None or user.role == auth.ROLE_ADMIN
        if is_admin:
            payload = await _admin_overview(runtime)
        else:
            payload = await _analyst_overview(runtime, user)
        response = render.render("overview.html", request=request, **payload)
        response.headers["Cache-Control"] = "no-store"
        return response


async def _admin_overview(runtime: Runtime) -> dict:
    environments = await runtime.store.list_environments()
    all_views = views.list_views(await runtime.store.list_all())
    totals = views.stats(all_views)
    problems = []
    for view in all_views:
        issues: list[str] = []
        if view.last_test_ok is False:
            issues.append("测试失败")
        if view.secret_fields and not view.secret_ok:
            issues.append("密钥不可用")
        if not issues:
            continue
        problems.append(
            {
                "environment_key": view.environment_key,
                "environment_title": view.environment_title,
                "name": view.name,
                "href": f"/targets/{view.id}/edit",
                "issues": issues,
            }
        )
        if len(problems) >= _ATTENTION_LIMIT:
            break
    rows, _total = await runtime.store.list_audit(since=_AUDIT_FLOOR, limit=_RECENT_LIMIT)
    titles = {item.key: item.title for item in environments}
    recent = [_audit_row(row, titles) for row in rows]
    return {
        "overview_admin": True,
        "environment_count": len(environments),
        "enabled_targets": totals.enabled,
        "failed": totals.failed,
        "key_issues": totals.key_issues,
        "problems": problems,
        "recent": recent,
    }


async def _analyst_overview(runtime: Runtime, user: auth.User) -> dict:
    environments = await runtime.store.list_environments()
    enabled_keys = {item.key for item in environments if item.enabled}
    all_views = views.list_views(await runtime.store.list_all())
    queryable = sum(
        1 for view in all_views if view.enabled and view.environment_key in enabled_keys
    )
    tokens = await auth.count_mcp_tokens(runtime.session_factory, user.id)
    since = datetime.now(UTC) - timedelta(hours=24)
    rows, total = await runtime.store.list_audit(
        since=since,
        action="tool.call",
        actor=user.username,
        limit=_RECENT_LIMIT,
    )
    calls = []
    for row in rows:
        detail = describe_summary(row.action, row.summary or "")
        parsed = detail.get("kind") == "tool"
        calls.append(
            {
                "at": row.created_at,
                "target": row.target_name or "—",
                "tool": detail.get("tool") if parsed else "—",
                "ok": bool(detail.get("ok")) if parsed else False,
                "error": detail.get("error") if parsed and not detail.get("ok") else "",
                "known": parsed,
            }
        )
    return {
        "overview_admin": False,
        "queryable": queryable,
        "token_count": tokens,
        "call_count": total,
        "calls": calls,
    }


def _audit_row(row, titles: dict[str, str]) -> dict:
    summary = row.summary or ""
    return {
        "at": row.created_at,
        "actor": row.actor,
        "action_label": action_label(row.action),
        "environment_key": row.environment_key,
        "environment_title": titles.get(row.environment_key or ""),
        "target_name": row.target_name,
        "summary": summary,
        "detail": describe_summary(row.action, summary),
    }
