"""首页概览：个人概览（所有角色）+ 管理概览（仅管理员）。"""

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
        payload = await _personal_overview(runtime, user)
        if user is None or user.role == auth.ROLE_ADMIN:
            payload["admin_signals"] = await _admin_signals(runtime)
        response = render.render("overview.html", request=request, **payload)
        response.headers["Cache-Control"] = "no-store"
        return response

    @server.custom_route("/admin/overview", methods=["GET"])
    async def admin_overview(request: Request) -> HTMLResponse:
        payload = await _admin_overview(runtime)
        response = render.render("admin_overview.html", request=request, **payload)
        response.headers["Cache-Control"] = "no-store"
        return response


def _attention_targets(all_views: list) -> list[dict]:
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
    return problems


async def _admin_signals(runtime: Runtime) -> dict:
    """管理员在个人概览上的入口摘要（不含页面细节）。"""
    all_views = views.list_views(await runtime.store.list_all())
    totals = views.stats(all_views)
    attention = len(_attention_targets(all_views))
    return {
        "attention": attention,
        "failed": totals.failed,
        "key_issues": totals.key_issues,
    }


async def _admin_overview(runtime: Runtime) -> dict:
    environments = await runtime.store.list_environments()
    all_views = views.list_views(await runtime.store.list_all())
    totals = views.stats(all_views)
    problems = _attention_targets(all_views)[:_ATTENTION_LIMIT]
    rows, _total = await runtime.store.list_audit(since=_AUDIT_FLOOR, limit=_RECENT_LIMIT)
    titles = {item.key: item.title for item in environments}
    recent = [_audit_row(row, titles) for row in rows]
    return {
        "environment_count": len(environments),
        "enabled_targets": totals.enabled,
        "failed": totals.failed,
        "key_issues": totals.key_issues,
        "problems": problems,
        "recent": recent,
    }


async def _personal_overview(runtime: Runtime, user: auth.User | None) -> dict:
    environments = await runtime.store.list_environments()
    enabled_keys = {item.key for item in environments if item.enabled}
    all_views = views.list_views(await runtime.store.list_all())
    queryable = sum(
        1 for view in all_views if view.enabled and view.environment_key in enabled_keys
    )
    if user is None:
        tokens = 0
        rows, total = [], 0
    else:
        tokens = await auth.count_mcp_tokens(runtime.session_factory, user.id)
        since = datetime.now(UTC) - timedelta(hours=24)
        rows, total = await runtime.store.list_audit(
            since=since,
            action="tool.call",
            actor=user.username,
            limit=_RECENT_LIMIT,
        )
    titles = {item.key: item.title for item in environments}
    calls = []
    for row in rows:
        detail = describe_summary(row.action, row.summary or "")
        parsed = detail.get("kind") == "tool"
        calls.append(
            {
                "at": row.created_at,
                "environment_key": row.environment_key,
                "environment_title": titles.get(row.environment_key or ""),
                "target": row.target_name or "—",
                "tool": detail.get("tool") if parsed else "—",
                "ok": bool(detail.get("ok")) if parsed else False,
                "error": detail.get("error") if parsed and not detail.get("ok") else "",
                "known": parsed,
            }
        )
    return {
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
        "error_detail": row.error_detail,
    }
