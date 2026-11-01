from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app

BASE_URL = "http://127.0.0.1"

COMMON = {"timeout_s": "15", "max_rows": "100", "max_bytes": "102400"}

PAYLOADS: dict[str, dict[str, str]] = {
    "mysql": {
        "type": "mysql",
        "name": "mysql-target",
        "enabled": "on",
        "host": "127.0.0.1",
        "port": "3306",
        "user": "u",
        "default_db": "app",
        "secret_password": "pw",
        **COMMON,
    },
    "mongo": {
        "type": "mongo",
        "name": "mongo-target",
        "enabled": "on",
        "host": "127.0.0.1",
        "port": "27017",
        "auth_source": "admin",
        "allowed_dbs": "app\npay",
        **COMMON,
    },
    "elasticsearch": {
        "type": "elasticsearch",
        "name": "es-target",
        "enabled": "on",
        "hosts": "http://127.0.0.1:9200",
        "allowed_indices": "orders\npay",
        "username": "u",
        "secret_password": "pw",
        **COMMON,
    },
    "redis": {
        "type": "redis",
        "name": "redis-target",
        "enabled": "on",
        "host": "127.0.0.1",
        "port": "6379",
        "db": "0",
        **COMMON,
    },
    "gitlab": {
        "type": "gitlab",
        "name": "gitlab-target",
        "enabled": "on",
        "base_url": "https://gitlab.example.com",
        "allowed_projects": "group/app",
        "secret_token": "tok",
        **COMMON,
    },
    "rabbitmq": {
        "type": "rabbitmq",
        "name": "rabbit-target",
        "enabled": "on",
        "management_url": "http://127.0.0.1:15672",
        "user": "guest",
        "allowed_vhosts": "/",
        "secret_password": "guest",
        **COMMON,
    },
    "kafka": {
        "type": "kafka",
        "name": "kafka-target",
        "enabled": "on",
        "bootstrap_servers": "127.0.0.1:9092",
        "security_protocol": "PLAINTEXT",
        "allowed_topics": "orders",
        **COMMON,
    },
    "cls": {
        "type": "cls",
        "name": "cls-target",
        "enabled": "on",
        "region": "ap-guangzhou",
        "allowed_topics": "logset/topic",
        "secret_secret_id": "id",
        "secret_secret_key": "key",
        **COMMON,
    },
}


def _client(runtime: Runtime) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=create_app(runtime.config, runtime)),
        base_url=BASE_URL,
    )


@pytest.mark.parametrize(("type_", "label"), [
    ("mysql", "MySQL"),
    ("mongo", "Mongo"),
    ("elasticsearch", "Elasticsearch"),
    ("redis", "Redis"),
    ("gitlab", "GitLab"),
    ("rabbitmq", "RabbitMQ"),
    ("kafka", "Kafka"),
    ("cls", "CLS"),
])
async def test_create_each_type(runtime: Runtime, type_: str, label: str) -> None:
    async with _client(runtime) as client:
        response = await client.post("/targets", data=PAYLOADS[type_])
        index = await client.get("/")

    assert response.status_code == 303
    target = await runtime.store.get(PAYLOADS[type_]["name"])
    assert target is not None and target.type == type_
    assert PAYLOADS[type_]["name"] in index.text
    assert label in index.text


async def test_new_form_and_unknown_type(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        form = await client.get("/targets/new?type=mysql")
        unknown = await client.get("/targets/new?type=oracle")

    assert form.status_code == 200
    assert "MySQL" in form.text and "密码" in form.text
    assert unknown.status_code == 400


async def test_post_unknown_type_rejected(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        response = await client.post(
            "/targets", data={"type": "oracle", "name": "oracle-target", **COMMON}
        )

    assert response.status_code == 400
    assert "未知的目标类型" in response.text


async def test_duplicate_name_rejected(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        response = await client.post("/targets", data=PAYLOADS["mysql"])

    assert response.status_code == 400
    assert "已存在" in response.text


async def test_invalid_name_rejected(runtime: Runtime) -> None:
    payload = dict(PAYLOADS["mysql"])
    payload["name"] = "Order-Mysql"

    async with _client(runtime) as client:
        response = await client.post("/targets", data=payload)

    assert response.status_code == 400
    assert "名称" in response.text


async def test_missing_required_secret_rejected(runtime: Runtime) -> None:
    payload = dict(PAYLOADS["mysql"])
    payload.pop("secret_password")

    async with _client(runtime) as client:
        response = await client.post("/targets", data=payload)

    assert response.status_code == 400
    assert "密码" in response.text


async def test_secret_not_displayed(runtime: Runtime) -> None:
    payload = dict(PAYLOADS["mysql"])
    payload["secret_password"] = "super-secret-value"

    async with _client(runtime) as client:
        await client.post("/targets", data=payload)
        target = await runtime.store.get("mysql-target")
        index = await client.get("/")
        edit = await client.get(f"/targets/{target.id}/edit")

    assert "super-secret-value" not in index.text
    assert "super-secret-value" not in edit.text
    assert "已设置" in edit.text


async def test_secret_keep_clear_and_replace(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        target = await runtime.store.get("mysql-target")

        keep = dict(PAYLOADS["mysql"])
        keep.pop("secret_password")
        await client.post(f"/targets/{target.id}", data=keep)
        kept = await runtime.store.get("mysql-target")
        assert kept.secret == {"password": "pw"}

        cleared = dict(keep)
        cleared["clear_password"] = "on"
        await client.post(f"/targets/{target.id}", data=cleared)
        cleared_target = await runtime.store.get("mysql-target")
        assert cleared_target.secret_fields == frozenset()

        replaced = dict(keep)
        replaced["secret_password"] = "new-pass"
        await client.post(f"/targets/{target.id}", data=replaced)
        replaced_target = await runtime.store.get("mysql-target")
        assert replaced_target.secret == {"password": "new-pass"}


async def test_toggle_and_delete(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["redis"])
        target = await runtime.store.get("redis-target")

        toggled = await client.post(f"/targets/{target.id}/toggle")
        disabled = await runtime.store.get("redis-target")
        confirm = await client.get(f"/targets/{target.id}/delete")
        removed = await client.post(f"/targets/{target.id}/delete")

    assert toggled.status_code == 303
    assert disabled.enabled is False
    assert confirm.status_code == 200 and "redis-target" in confirm.text
    assert removed.status_code == 303
    assert await runtime.store.get("redis-target") is None


async def test_test_connection_failure_recorded(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        target = await runtime.store.get("mysql-target")
        await client.post(f"/targets/{target.id}/test")
        index = await client.get("/")

    tested = await runtime.store.get("mysql-target")
    assert tested.last_test_ok is False
    assert tested.last_test_error
    assert "mysql" in tested.last_test_error.lower()
    assert "pw" not in tested.last_test_error
    assert "失败" in index.text


async def test_test_connection_success_recorded(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(name: str, connector) -> None:
        return None

    monkeypatch.setattr(runtime.catalog, "test_connection", fake)
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["redis"])
        target = await runtime.store.get("redis-target")
        await client.post(f"/targets/{target.id}/test")

    tested = await runtime.store.get("redis-target")
    assert tested.last_test_ok is True


async def test_settings_page_and_update(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        page = await client.get("/settings")
        saved = await client.post(
            "/settings",
            data={"audit_retention_days": "30", "target_max_concurrency": "5"},
        )
        after = await client.get("/settings")
        invalid = await client.post(
            "/settings",
            data={"audit_retention_days": "0", "target_max_concurrency": "10"},
        )

    assert page.status_code == 200 and "90" in page.text and "10" in page.text
    assert saved.status_code == 303
    assert "30" in after.text and "5" in after.text
    assert await runtime.store.get_settings() == {
        "audit_retention_days": "30",
        "target_max_concurrency": "5",
    }
    assert invalid.status_code == 400


async def test_cross_site_post_rejected(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        response = await client.post(
            "/targets",
            data=PAYLOADS["mysql"],
            headers={"origin": "http://evil.example"},
        )

    assert response.status_code == 403
    assert await runtime.store.get("mysql-target") is None


async def test_unknown_target_404(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        for method, path in [
            ("GET", "/targets/999/edit"),
            ("POST", "/targets/999/toggle"),
            ("GET", "/targets/999/delete"),
            ("POST", "/targets/999/delete"),
            ("POST", "/targets/999/test"),
        ]:
            response = await client.request(method, path)
            assert response.status_code == 404, (method, path)
