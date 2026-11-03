from __future__ import annotations

import httpx
from httpx import ASGITransport

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app
from dr_panda_mcp.store.protocol import AuditEntry
from dr_panda_mcp.web.audit_page import describe_summary

BASE_URL = "http://127.0.0.1"


def _client(runtime: Runtime, locale: str | None = "zh-Hans") -> httpx.AsyncClient:
    kwargs = {"cookies": {"drpanda_lang": locale}} if locale else {}
    return httpx.AsyncClient(
        transport=ASGITransport(app=create_app(runtime.config, runtime, auth_required=False)),
        base_url=BASE_URL,
        **kwargs,
    )


async def test_audit_page_lists_and_filters(runtime: Runtime) -> None:
    await runtime.store.append_audit(
        AuditEntry(
            actor="admin",
            action="tool.call",
            target_name="order-mysql",
            summary=(
                "client=cursor prefix=P2dc7BWnV8jL mysql_query env=default "
                "target=order-mysql "
                'params={"sql": "SHOW TABLES LIKE \'%share%\'", "limit": 40} '
                "returned=6 elapsed_ms=122 error=-"
            ),
            environment_key="default",
        )
    )
    await runtime.store.append_audit(
        AuditEntry(
            actor="admin",
            action="settings.update",
            summary="audit_retention_days: 90 -> 30",
        )
    )

    async with _client(runtime) as client:
        page = await client.get("/audit")
        narrowed = await client.get(
            "/audit", params={"action": "tool.call", "env": "default", "q": "order"}
        )
        empty = await client.get("/audit", params={"q": "no-such-object"})

    assert page.status_code == 200
    assert "<h1>审计</h1>" in page.text
    assert page.text.count("<h1") == 1
    assert 'aria-current="page"' in page.text
    assert "工具调用" in page.text
    assert "order-mysql" in page.text
    assert "修改配置" in page.text
    assert "近 24 小时" in page.text
    assert "order-mysql" in narrowed.text
    assert "audit_retention_days" not in narrowed.text
    assert "没有符合条件的记录" in empty.text
    assert "清除筛选" in empty.text
    assert 'data-dialog-open="audit-summary-' in page.text
    assert "查看" in page.text
    assert "SHOW TABLES LIKE" in page.text
    assert "返回条数" in page.text
    assert "参数在记录时已截短" not in page.text

    async with _client(runtime, locale=None) as client:
        english = await client.get("/audit")

    assert "<title>Audit · DrPanda MCP</title>" in english.text
    assert "Last 24 hours" in english.text
    assert "Tool call" in english.text
    assert "Nothing happened" not in english.text
    assert "View" in english.text
    assert "Parameters" in english.text
    assert "Rows returned" in english.text
    assert "查看" not in english.text


def test_tool_summary_splits_sql_and_keeps_a_returned_inside_it() -> None:
    params = '{"sql": "SELECT 1 AS returned=2 FROM t", "limit": 40}'
    summary = (
        "client=cursor prefix=P2dc7BWnV8jL mysql_query env=default target=test-mysql "
        f"params={params} returned=6 elapsed_ms=122 error=-"
    )

    detail = describe_summary("tool.call", summary)

    assert detail["kind"] == "tool"
    assert detail["preview"].startswith("mysql_query · SELECT 1 AS returned=2 FROM t")
    assert detail["client"] == "cursor"
    assert detail["prefix"] == "P2dc7BWnV8jL"
    assert detail["returned"] == "6"
    assert detail["elapsed_ms"] == "122"
    assert detail["ok"] is True
    assert detail["params_sql"] == "SELECT 1 AS returned=2 FROM t"
    assert detail["params_fields"] == [("limit", "40")]
    assert detail["params_raw"] == ""


def test_tool_summary_without_the_suffix_stays_plain() -> None:
    summary = "mysql_query env=default target=order-mysql"

    detail = describe_summary("tool.call", summary)

    assert detail["kind"] == "plain"
    assert detail["preview"] == summary


def test_cut_json_is_marked_truncated() -> None:
    summary = (
        "client=cursor prefix=abc mysql_query env=default target=test-mysql "
        'params={"sql": "SELECT 1 FROM " returned=1 elapsed_ms=9 error=UPSTREAM_TIMEOUT'
    )

    detail = describe_summary("tool.call", summary)

    assert detail["kind"] == "tool"
    assert detail["ok"] is False
    assert detail["error"] == "UPSTREAM_TIMEOUT"
    assert "UPSTREAM_TIMEOUT" in detail["preview"]
    assert detail["params_raw"].startswith('{"sql"')
    assert detail["params_sql"] == ""
