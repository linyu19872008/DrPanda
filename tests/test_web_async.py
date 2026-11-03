"""异步交互（frontend-js-policy v2）：JSON 双模式、探测接口与保存门槛。"""

from __future__ import annotations

import re

import httpx
import pytest
from httpx import ASGITransport

from dr_panda_mcp import auth
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app

BASE_URL = "http://127.0.0.1"
JSON = {"accept": "application/json"}
COMMON = {"timeout_s": "15", "max_rows": "100", "max_bytes": "102400"}
MYSQL = {
    "type": "mysql",
    "name": "mysql-target",
    "enabled": "on",
    "host": "127.0.0.1",
    "port": "3306",
    "user": "u",
    "default_db": "app",
    "secret_password": "pw",
    **COMMON,
}


def _client(runtime: Runtime) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=create_app(runtime.config, runtime, auth_required=False)),
        base_url=BASE_URL,
        cookies={"drpanda_lang": "zh-Hans"},
    )


@pytest.fixture
def probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from dr_panda_mcp.web import routes as routes_module

    async def fake_probe(draft, existing):
        return {
            "ok": True,
            "message": "连接测试通过，可以保存。",
            "code": None,
            "checked_at": "2026-11-03 00:00:00 UTC",
            "duration_ms": 3,
        }

    monkeypatch.setattr(routes_module, "_test_draft_target", fake_probe)


@pytest.fixture
def probe_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from dr_panda_mcp.web import routes as routes_module

    async def fake_probe(draft, existing):
        return {
            "ok": False,
            "message": "上游连接超时（已脱敏）",
            "code": "UPSTREAM_TIMEOUT",
            "checked_at": "2026-11-03 00:00:00 UTC",
            "duration_ms": 15000,
        }

    monkeypatch.setattr(routes_module, "_test_draft_target", fake_probe)


# ---------------------------------------------------------------------------
# 探测接口：真实探测、不写库
# ---------------------------------------------------------------------------
async def test_probe_json_success_does_not_save(runtime: Runtime, probe_ok) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets/probe", data=MYSQL, headers=JSON)
        target = await runtime.store.get("mysql-target")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"]
    assert payload["checked_at"]
    assert payload["duration_ms"] == 3
    assert target is None


async def test_probe_json_failure_is_reported(runtime: Runtime, probe_fail) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets/probe", data=MYSQL, headers=JSON)
        target = await runtime.store.get("mysql-target")

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "PROBE_FAILED"
    assert payload["phase"] == "probe"
    assert "上游连接超时" in payload["message"]
    assert target is None


async def test_probe_json_invalid_input_returns_field_errors(runtime: Runtime, probe_ok) -> None:
    payload = dict(MYSQL)
    payload.pop("secret_password")

    async with _client(runtime) as client:
        response = await client.post("/targets/probe", data=payload, headers=JSON)

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "INVALID_INPUT"
    assert "secret_password" in body["errors"]


async def test_probe_unknown_target_returns_json_404(runtime: Runtime, probe_ok) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets/999/probe", data=MYSQL, headers=JSON)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_edit_probe_uses_saved_secret(runtime: Runtime, probe_ok) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=MYSQL)
        target = await runtime.store.get("mysql-target")
        payload = dict(MYSQL)
        payload.pop("secret_password")
        response = await client.post(
            f"/targets/{target.id}/probe", data=payload, headers=JSON
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True


# ---------------------------------------------------------------------------
# 保存门槛：服务端保存前必探测，失败不落库
# ---------------------------------------------------------------------------
async def test_save_json_with_probe_failure_does_not_write(
    runtime: Runtime, probe_fail
) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets", data=MYSQL, headers=JSON)
        target = await runtime.store.get("mysql-target")

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["phase"] == "probe"
    assert target is None


async def test_save_json_with_probe_success_writes(runtime: Runtime, probe_ok) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets", data=MYSQL, headers=JSON)
        target = await runtime.store.get("mysql-target")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["redirect"].startswith("/?flash=created")
    assert "env=" in body["redirect"]
    assert target is not None
    # 保存时的探测结果落库，列表页不再显示“未测试”
    assert target.last_test_ok is True


async def test_save_json_conflict_returns_errors(runtime: Runtime, probe_ok) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=MYSQL, headers=JSON)
        response = await client.post("/targets", data=MYSQL, headers=JSON)

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert "_form" in body["errors"]


async def test_save_html_probes_before_write(runtime: Runtime, probe_fail) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets", data=MYSQL)
        target = await runtime.store.get("mysql-target")

    assert response.status_code == 400
    assert "连接测试失败" in response.text
    assert target is None


async def test_save_html_success_still_redirects(runtime: Runtime, probe_ok) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets", data=MYSQL)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?flash=created")
    assert "env=" in response.headers["location"]


# ---------------------------------------------------------------------------
# 列表行内动作与设置保存的 JSON 响应
# ---------------------------------------------------------------------------
async def test_list_test_and_toggle_json(runtime: Runtime, probe_ok, monkeypatch) -> None:
    async def fake_connection(name: str, connector, **_kwargs) -> None:
        return None

    monkeypatch.setattr(runtime.catalog, "test_connection", fake_connection)
    async with _client(runtime) as client:
        await client.post("/targets", data=MYSQL)
        target = await runtime.store.get("mysql-target")
        tested = await client.post(f"/targets/{target.id}/test", headers=JSON)
        toggled = await client.post(f"/targets/{target.id}/toggle", headers=JSON)

    tested_body = tested.json()
    assert tested.status_code == 200
    assert tested_body["test_ok"] is True
    assert tested_body["test_time"]
    assert "stats" in tested_body

    toggled_body = toggled.json()
    assert toggled.status_code == 200
    assert toggled_body["enabled"] is False
    assert toggled_body["label"] == "已停用"


async def test_settings_save_json(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        response = await client.post(
            "/settings",
            data={"section": "runtime", "audit_retention_days": "30"},
            headers=JSON,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["section"] == "runtime"
    stored = await runtime.store.get_settings()
    assert stored["audit_retention_days"] == "30"


async def test_settings_save_json_returns_field_errors(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        response = await client.post(
            "/settings",
            data={"section": "runtime", "audit_retention_days": "0"},
            headers=JSON,
        )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_INPUT"
    assert "audit_retention_days" in body["errors"]


# ---------------------------------------------------------------------------
# 安全外壳：JSON 401/403、CSP
# ---------------------------------------------------------------------------
async def test_json_unauthorized_returns_401(runtime: Runtime) -> None:
    from dr_panda_mcp.web import security

    async def app(scope, receive, send):  # pragma: no cover - 不会走到内层
        raise AssertionError("request should be rejected")

    inner = security.AuthMiddleware(
        app, runtime=runtime, session_key=b"0" * 32, auth_required=True
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=inner), base_url=BASE_URL
    ) as client:
        response = await client.post("/targets", data={}, headers=JSON)

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["login"].startswith("/login?next=")


async def test_json_csrf_failure_returns_403(runtime: Runtime) -> None:
    from dr_panda_mcp.web import security

    async def app(scope, receive, send):  # pragma: no cover - 不会走到内层
        raise AssertionError("request should be rejected")

    inner = security.CSRFMiddleware(app)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=inner), base_url=BASE_URL
    ) as client:
        response = await client.post("/targets", data={"name": "x"}, headers=JSON)

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_EXPIRED"


async def test_security_headers_are_present(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        response = await client.get("/")

    csp = response.headers.get("content-security-policy", "")
    assert "script-src 'self'" in csp
    assert "connect-src 'self'" in csp
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"


async def test_login_json_error_and_success(runtime: Runtime) -> None:
    cfg = runtime.config
    app = create_app(cfg, runtime, auth_required=True)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url=BASE_URL,
        cookies={"drpanda_lang": "zh-Hans"},
    ) as client:
        page = await client.get("/login")
        token = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
        failed = await client.post(
            "/login",
            data={"_csrf": token, "username": "admin", "password": "wrong"},
            headers=JSON,
        )

    assert failed.status_code == 401
    body = failed.json()
    assert body["ok"] is False
    assert body["code"] == "AUTH_FAILED"


async def test_duplicate_name_reported_before_probe(
    runtime: Runtime, probe_ok, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重名应在探测之前报错，不能被“探测失败”掩盖。"""
    from dr_panda_mcp.web import routes as routes_module

    async with _client(runtime) as client:
        await client.post("/targets", data=MYSQL, headers=JSON)

    async def fake_probe(draft, existing):
        return {
            "ok": False,
            "message": "上游不可用",
            "code": None,
            "checked_at": "2026-11-03 00:00:00 UTC",
            "duration_ms": 1,
        }

    monkeypatch.setattr(routes_module, "_test_draft_target", fake_probe)
    async with _client(runtime) as client:
        response = await client.post("/targets", data=MYSQL, headers=JSON)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_INPUT"
    assert "已存在" in body["errors"]["_form"]


async def test_login_json_success_redirects(runtime: Runtime) -> None:
    await auth.create_admin(
        runtime.session_factory, password_hash=auth.hash_password("abcdefgh")
    )
    app = create_app(runtime.config, runtime, auth_required=True)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url=BASE_URL,
        cookies={"drpanda_lang": "zh-Hans"},
    ) as client:
        page = await client.get("/login")
        token = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
        response = await client.post(
            "/login",
            data={"_csrf": token, "username": "admin", "password": "abcdefgh"},
            headers=JSON,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["redirect"] == "/"
    assert auth.SESSION_COOKIE in response.cookies


async def test_edit_limit_only_skips_probe(runtime: Runtime, probe_ok, monkeypatch) -> None:
    from dr_panda_mcp.web import routes as routes_module

    calls = {"n": 0}

    async def counting(draft, existing):
        calls["n"] += 1
        return {"ok": False, "message": "不应探测", "code": "UPSTREAM_TIMEOUT"}

    async with _client(runtime) as client:
        created = await client.post("/targets", data=MYSQL, headers=JSON)
        assert created.status_code == 200
        target = await runtime.store.get("mysql-target")
        assert target is not None
        monkeypatch.setattr(routes_module, "_test_draft_target", counting)
        payload = dict(MYSQL)
        payload.pop("secret_password")
        payload["max_rows"] = "50"
        payload["allowed_dbs"] = "app"
        response = await client.post(f"/targets/{target.id}", data=payload, headers=JSON)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert calls["n"] == 0
    updated = await runtime.store.get("mysql-target")
    assert updated is not None
    assert updated.options["max_rows"] == 50
