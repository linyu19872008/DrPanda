from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from httpx import ASGITransport

from dr_panda_mcp.errors import INTERNAL, UPSTREAM_UNAVAILABLE
from dr_panda_mcp.log import database_kind, format_event, log_tool_call
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app
from dr_panda_mcp.store.protocol import AuditEntry
from dr_panda_mcp.tools.base import build_tool_summary, write_tool_audit
from dr_panda_mcp.web.audit_page import describe_summary


def test_database_kind_hides_the_url() -> None:
    url = "mysql+asyncmy://app:s3cret@db.internal:3306/panda"

    assert database_kind(url) == "mysql"
    assert database_kind("postgresql+asyncpg://u:pw@localhost/db") == "postgres"
    assert database_kind("sqlite+aiosqlite:////tmp/dr-panda.sqlite") == "sqlite"
    assert "s3cret" not in database_kind(url)


def test_format_event_omits_empty_fields() -> None:
    line = format_event("tool.call", "完成", tool="mysql_query", env="", request="ab12cd34")

    assert line == "tool.call request=ab12cd34 tool=mysql_query 完成"


def test_success_log_leaves_the_sql_out(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="dr_panda_mcp.log"):
        log_tool_call(
            tool="mysql_query",
            target_name="gift-mysql",
            environment_key="default",
            returned=20,
            started=0,
            error_code=None,
            debug_hint='{"sql": "SELECT secret FROM t"}',
        )

    assert "tool.call" in caplog.text
    assert "SELECT" not in caplog.text
    assert "error=-" in caplog.text


def test_debug_log_keeps_a_redacted_hint(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="dr_panda_mcp.log"):
        log_tool_call(
            tool="mysql_query",
            target_name="gift-mysql",
            environment_key="default",
            returned=1,
            started=0,
            error_code=None,
            debug_hint="SELECT *** FROM t " + ("column " * 40),
        )

    debug = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert debug
    assert "SELECT ***" in debug[0]
    assert "error=-" in debug[0]


def test_upstream_failure_has_no_traceback(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="dr_panda_mcp.log"):
        log_tool_call(
            tool="mysql_query",
            target_name="gift-mysql",
            environment_key="default",
            returned=0,
            started=0,
            error_code=UPSTREAM_UNAVAILABLE,
            error_message="mysql 查询失败：mysql://app:s3cret@db/panda SECRETVALUE",
            secrets=["SECRETVALUE"],
        )

    assert "upstream.error" in caplog.text
    assert "s3cret" not in caplog.text
    assert "SECRETVALUE" not in caplog.text
    assert "Traceback" not in caplog.text
    assert "***" in caplog.text


def test_internal_failure_redacts_the_traceback(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="dr_panda_mcp.log"):
        try:
            raise RuntimeError("boom SECRETVALUE mysql://app:s3cret@db/panda")
        except RuntimeError:
            log_tool_call(
                tool="mysql_query",
                target_name="gift-mysql",
                environment_key="default",
                returned=0,
                started=0,
                error_code=INTERNAL,
                error_message="boom SECRETVALUE mysql://app:s3cret@db/panda",
                secrets=["SECRETVALUE"],
            )

    assert "Traceback" in caplog.text
    assert "SECRETVALUE" not in caplog.text
    assert "s3cret" not in caplog.text


def test_summary_carries_the_request_id() -> None:
    summary = build_tool_summary(
        tool="mysql_query",
        name="gift-mysql",
        environment_key="default",
        params={"sql": "SELECT 1", "limit": 20},
        target=None,
        returned=1,
        elapsed_ms=4,
        error_code=None,
        request_id="ab12cd34",
    )

    detail = describe_summary("tool.call", summary)

    assert summary.endswith("request=ab12cd34")
    assert detail["request"] == "ab12cd34"
    assert detail["params_sql"] == "SELECT 1"
    assert ("limit", "20") in detail["params_fields"]


async def test_written_audit_uses_the_active_request_id(runtime: Runtime, caplog) -> None:
    from dr_panda_mcp.log import _REQUEST_ID

    token = _REQUEST_ID.set("ab12cd34")
    try:
        with caplog.at_level(logging.INFO, logger="dr_panda_mcp.log"):
            await write_tool_audit(
                runtime,
                tool="mysql_query",
                name="gift-mysql",
                environment_key="default",
                params={"sql": "SELECT 1"},
                target=None,
                returned=1,
                started=0,
                error_code=None,
            )
    finally:
        _REQUEST_ID.reset(token)

    rows, _total = await runtime.store.list_audit(since=datetime(2000, 1, 1, tzinfo=UTC))
    assert rows[0].summary.endswith("request=ab12cd34")
    assert "tool.call" in caplog.text
    assert "SELECT 1" not in caplog.text


async def test_failed_tool_audit_keeps_error_detail(runtime: Runtime) -> None:
    await write_tool_audit(
        runtime,
        tool="mysql_query",
        name="gift-mysql",
        environment_key="default",
        params={"sql": "SELECT 1"},
        target=None,
        returned=0,
        started=0,
        error_code="UPSTREAM_UNAVAILABLE",
        error_message="连接被拒绝",
    )
    await write_tool_audit(
        runtime,
        tool="mysql_query",
        name="gift-mysql",
        environment_key="default",
        params={"sql": "SELECT 2"},
        target=None,
        returned=0,
        started=0,
        error_code="UPSTREAM_UNAVAILABLE",
        error_message="x" * 600,
    )

    rows, _total = await runtime.store.list_audit(since=datetime(2000, 1, 1, tzinfo=UTC))
    by_summary = {row.summary: row for row in rows}
    refused = next(row for summary, row in by_summary.items() if "SELECT 1" in summary)
    assert refused.error_detail == "连接被拒绝"
    assert refused.outcome == "failed"
    long_row = next(row for summary, row in by_summary.items() if "SELECT 2" in summary)
    assert len(long_row.error_detail or "") == 512


async def test_audit_dialog_shows_the_request_id(runtime: Runtime) -> None:
    await runtime.store.append_audit(
        AuditEntry(
            actor="admin",
            action="tool.call",
            target_name="gift-mysql",
            summary=(
                "mysql_query env=default target=gift-mysql "
                'params={"sql": "SELECT 1", "limit": 5} '
                "returned=1 elapsed_ms=4 error=- request=ab12cd34"
            ),
            environment_key="default",
        )
    )
    app = create_app(runtime.config, runtime, auth_required=False)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        page = await client.get("/audit", cookies={"drpanda_lang": "zh-Hans"})
        english = await client.get("/audit", cookies={"drpanda_lang": "en"})

    assert "请求号" in page.text
    assert "ab12cd34" in page.text
    assert "Request" in english.text


async def test_http_log_skips_quiet_paths(runtime: Runtime, caplog) -> None:
    app = create_app(runtime.config, runtime, auth_required=False)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with caplog.at_level(logging.INFO, logger="dr_panda_mcp.log"):
            health = await client.get("/healthz")
            static = await client.get("/static/app.css")
            page = await client.get("/audit")

    assert len(health.headers["x-request-id"]) == 8
    assert len(static.headers["x-request-id"]) == 8
    assert len(page.headers["x-request-id"]) == 8
    assert "/healthz" not in caplog.text
    assert "/static/" not in caplog.text
    assert "GET /audit 200" in caplog.text
    assert f"request={page.headers['x-request-id']}" in caplog.text
