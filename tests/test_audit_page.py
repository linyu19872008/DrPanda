from __future__ import annotations

import httpx
from httpx import ASGITransport

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app
from dr_panda_mcp.store.protocol import AuditEntry

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
            summary="mysql_query env=default target=order-mysql",
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

    async with _client(runtime, locale=None) as client:
        english = await client.get("/audit")

    assert "<title>Audit · DrPanda MCP</title>" in english.text
    assert "Last 24 hours" in english.text
    assert "Tool call" in english.text
    assert "Nothing happened" not in english.text
