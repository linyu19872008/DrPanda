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
        rejected = await client.post(f"/targets/{target.id}", data=cleared)
        cleared_target = await runtime.store.get("mysql-target")
        assert rejected.status_code == 400
        assert "不能为空" in rejected.text
        assert cleared_target.secret_fields == frozenset({"password"})

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


async def test_test_connection_failure_recorded(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dr_panda_mcp import errors

    async def failing(name: str, connector) -> None:
        raise errors.UpstreamUnavailable("mysql 模拟连接失败")

    monkeypatch.setattr(runtime.catalog, "test_connection", failing)

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


# ---------------------------------------------------------------------------
# 界面骨架、主题与静态资源
# ---------------------------------------------------------------------------
async def test_index_shell_and_default_theme(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        page = await client.get("/")

    text = page.text
    assert '<html lang="zh-CN">' in text
    assert 'class="skip-link"' in text
    assert 'id="main"' in text
    assert 'aria-current="page"' in text
    assert 'aria-label="主导航"' in text
    assert 'name="mode" value="dark"' in text
    assert "/static/app.css?v=" in text
    assert "还没有登记任何目标" in text
    assert text.count("<h1") == 1


async def test_theme_cookie_roundtrip(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        dark = await client.post("/theme", data={"mode": "dark", "next": "/"})
        page = await client.get("/")
        assert dark.status_code == 303
        assert dark.headers["location"] == "/"
        assert 'data-theme="dark"' in page.text

        await client.post("/theme", data={"mode": "light", "next": "/"})
        page = await client.get("/")
        assert 'data-theme="light"' in page.text

        await client.post("/theme", data={"mode": "system", "next": "/"})
        page = await client.get("/")
        assert '<html lang="zh-CN">' in page.text


async def test_theme_rejects_open_redirect(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        response = await client.post(
            "/theme", data={"mode": "dark", "next": "//evil.example/x"}
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


async def test_static_css_route(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        first = await client.get("/static/app.css")
        cached = await client.get(
            "/static/app.css", headers={"if-none-match": first.headers["etag"]}
        )
        missing = await client.get("/static/nope.css")

    assert first.status_code == 200
    assert "text/css" in first.headers["content-type"]
    assert "--accent" in first.text
    assert first.headers.get("etag")
    assert cached.status_code == 304
    assert missing.status_code == 404


async def test_type_chooser_page(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        page = await client.get("/targets/new")

    assert page.status_code == 200
    assert "选择目标类型" in page.text
    for label in ["MySQL", "Mongo", "Elasticsearch", "Redis", "GitLab", "RabbitMQ", "Kafka", "CLS"]:
        assert label in page.text
    assert "/targets/new?type=mysql" in page.text


# ---------------------------------------------------------------------------
# 搜索、筛选、统计与反馈
# ---------------------------------------------------------------------------
async def test_search_and_type_filter(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        await client.post("/targets", data=PAYLOADS["redis"])

        search = await client.get("/", params={"q": "mysql-target"})
        filtered = await client.get("/", params={"type": "redis"})
        no_match = await client.get("/", params={"q": "no-such-target"})

    assert "mysql-target" in search.text
    assert "redis-target" not in search.text
    assert "redis-target" in filtered.text
    assert "mysql-target" not in filtered.text
    assert "没有匹配的目标" in no_match.text


async def test_stats_and_flash_messages(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        created = await client.post("/targets", data=PAYLOADS["redis"])
        location = created.headers["location"]
        page = await client.get(location)
        target = await runtime.store.get("redis-target")

        toggled = await client.post(f"/targets/{target.id}/toggle")
        toggled_page = await client.get(toggled.headers["location"])

        deleted = await client.post(f"/targets/{target.id}/delete")
        deleted_page = await client.get(deleted.headers["location"])

    assert "flash=created" in location
    assert "目标已创建" in page.text
    assert "目标总数" in page.text
    assert "启用状态已切换" in toggled_page.text
    assert "目标已删除" in deleted_page.text


# ---------------------------------------------------------------------------
# 表单与错误页
# ---------------------------------------------------------------------------
async def test_form_sections_and_error_summary(runtime: Runtime) -> None:
    payload = dict(PAYLOADS["mysql"])
    payload.pop("secret_password")

    async with _client(runtime) as client:
        form = await client.get("/targets/new?type=mysql")
        invalid = await client.post("/targets", data=payload)

    assert form.status_code == 200
    for section in ["基本信息", "连接", "授权范围", "密钥", "运行限制"]:
        assert section in form.text
    assert 'name="secret_password"' in form.text
    assert invalid.status_code == 400
    assert "有 1 处需要修改" in invalid.text
    assert 'aria-invalid="true"' in invalid.text
    assert "#err-secret_password" in invalid.text


async def test_edit_form_shows_secret_badge(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        target = await runtime.store.get("mysql-target")
        page = await client.get(f"/targets/{target.id}/edit")

    assert page.status_code == 200
    assert "已设置" in page.text
    assert "清除已保存的密钥" in page.text
    assert "value=\"pw\"" not in page.text


async def test_html_error_pages(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        not_found = await client.get("/targets/999/edit")
        bad_type = await client.get("/targets/new?type=oracle")

    assert not_found.status_code == 404
    assert "找不到目标" in not_found.text
    assert "返回排查目标" in not_found.text
    assert bad_type.status_code == 400
    assert "未知的目标类型" in bad_type.text


async def test_table_accessibility_markup(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        page = await client.get("/")

    assert page.text.count('scope="col"') >= 6
    assert 'aria-label="按类型筛选"' in page.text
    assert 'class="status status--none"' in page.text


async def test_no_javascript_and_css_budget(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        pages = [
            await client.get("/"),
            await client.get("/targets/new?type=mysql"),
            await client.get("/settings"),
        ]
        css = await client.get("/static/app.css")

    for page in pages:
        assert "<script" not in page.text
    assert len(css.content) < 40_000


async def test_required_secret_cannot_be_cleared_on_edit(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        await client.post("/targets", data=PAYLOADS["mysql"])
        target = await runtime.store.get("mysql-target")
        payload = dict(PAYLOADS["mysql"])
        payload["clear_password"] = "on"
        payload.pop("secret_password", None)
        response = await client.post(f"/targets/{target.id}", data=payload)

    assert response.status_code == 400
    assert "不能为空" in response.text
    stored = await runtime.store.get("mysql-target")
    assert stored is not None and "password" in stored.secret_fields


def test_theme_next_rejects_backslash_variants() -> None:
    from dr_panda_mcp.web.theme import safe_next

    assert safe_next("/") == "/"
    assert safe_next("/settings?x=1") == "/settings?x=1"
    assert safe_next("/\\evil.example") == "/"
    assert safe_next("/%5Cevil.example") == "/"
    assert safe_next("//evil.example") == "/"


async def test_ca_pem_validation_and_persistence(runtime: Runtime) -> None:
    from tests.test_connectors_data import _ca_pem

    async with _client(runtime) as client:
        form = await client.get("/targets/new?type=mysql")
        invalid = dict(PAYLOADS["mysql"])
        invalid["ssl"] = "on"
        invalid["ca_pem"] = "not a certificate"
        bad = await client.post("/targets", data=invalid)

        no_ssl = dict(PAYLOADS["mysql"])
        no_ssl["ca_pem"] = _ca_pem()
        rejected = await client.post("/targets", data=no_ssl)

        valid = dict(PAYLOADS["mysql"])
        valid["ssl"] = "on"
        valid["ca_pem"] = _ca_pem()
        created = await client.post("/targets", data=valid)
        target = await runtime.store.get("mysql-target")

    assert "CA 证书 PEM" in form.text
    assert bad.status_code == 400 and "CA 证书不是合法 PEM" in bad.text
    assert rejected.status_code == 400 and "必须启用 SSL" in rejected.text
    assert created.status_code == 303
    assert target is not None and target.options["ca_pem"].startswith("-----BEGIN CERTIFICATE-----")


async def test_client_cert_pair_validation(runtime: Runtime) -> None:
    async with _client(runtime) as client:
        only_cert = dict(PAYLOADS["mysql"])
        only_cert["ssl"] = "on"
        only_cert["secret_client_cert"] = "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----"
        rejected = await client.post("/targets", data=only_cert)

        both = dict(only_cert)
        both["secret_client_key"] = "-----BEGIN PRIVATE KEY-----\ny\n-----END PRIVATE KEY-----"
        created = await client.post("/targets", data=both)
        target = await runtime.store.get("mysql-target")

    assert rejected.status_code == 400
    assert "必须同时提供" in rejected.text
    assert created.status_code == 303
    assert target is not None
    assert {"client_cert", "client_key"} <= target.secret_fields
    assert target.secret["client_key"].startswith("-----BEGIN PRIVATE KEY-----")


async def test_mongo_auth_mode_validation(runtime: Runtime) -> None:
    base = {
        "type": "mongo",
        "name": "mongo-auth-target",
        "enabled": "on",
        "port": "27017",
        "auth_source": "admin",
        "allowed_dbs": "app",
        **COMMON,
    }

    async with _client(runtime) as client:
        none_with_user = dict(base)
        none_with_user["user"] = "ro"
        rejected = await client.post("/targets", data=none_with_user)

        password_missing = dict(base)
        password_missing["auth_mode"] = "password"
        password_missing["host"] = "127.0.0.1"
        password_missing["user"] = "ro"
        missing = await client.post("/targets", data=password_missing)

        password_ok = dict(password_missing)
        password_ok["secret_password"] = "pw"
        created = await client.post("/targets", data=password_ok)
        target = await runtime.store.get("mongo-auth-target")

        uri_with_host = dict(base)
        uri_with_host["auth_mode"] = "uri"
        uri_with_host["host"] = "127.0.0.1"
        uri_with_host["secret_uri"] = "mongodb://127.0.0.1:27017/"
        conflict = await client.post("/targets", data=uri_with_host)

    assert rejected.status_code == 400 and "不能填写" in rejected.text
    assert missing.status_code == 400 and "密码" in missing.text
    assert created.status_code == 303
    assert target is not None and target.options["auth_mode"] == "password"
    assert target.secret_fields == frozenset({"password"})
    assert conflict.status_code == 400 and "必须留空" in conflict.text
