"""分析员角色、概览和首次改密。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from httpx import ASGITransport

from dr_panda_mcp import auth
from dr_panda_mcp.config import Config
from dr_panda_mcp.runtime import create_runtime
from dr_panda_mcp.server import create_app
from dr_panda_mcp.store.protocol import AuditEntry, SecretPatch, TargetDraft
from dr_panda_mcp.web import i18n

BASE = "http://127.0.0.1"
SECRET = "super-secret-db-password"


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8111,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        secret_key_b64=None,
        log_level="INFO",
        install_file=tmp_path / "install.json",
        install_key_file=tmp_path / "install.key",
        session_key_file=tmp_path / "session.key",
    )


async def _admin_app(tmp_path: Path):
    cfg = _config(tmp_path)
    runtime = await create_runtime(cfg, key_file=tmp_path / "secret.key")
    await auth.create_admin(runtime.session_factory, password_hash=auth.hash_password("abcdefgh"))
    key = auth.load_or_create_session_key(cfg.session_key_file)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    return runtime, app


async def _login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    await client.get("/login")
    csrf = client.cookies.get(auth.CSRF_COOKIE)
    return await client.post(
        "/login",
        data={"_csrf": csrf, "username": username, "password": password},
        follow_redirects=False,
    )


async def test_analyst_is_limited_to_own_pages(tmp_path: Path) -> None:
    runtime, app = await _admin_app(tmp_path)
    created_target = await runtime.store.create(
        TargetDraft(
            name="mysql-target",
            type="mysql",
            enabled=True,
            options={
                "host": "10.1.1.1",
                "user": "root",
                "default_db": "live",
                "allowed_dbs": ["live", "logs"],
            },
            secret_patch=SecretPatch(set={"password": SECRET}),
            environment_key="default",
        ),
        "admin",
    )
    await runtime.store.record_test(created_target.id, False, "connection refused", "admin")
    await runtime.store.create_environment("legacy", "旧环境", "admin", enabled=False)
    await runtime.store.create(
        TargetDraft(
            name="legacy-mysql",
            type="mysql",
            enabled=False,
            options={"host": "10.9.9.9", "allowed_dbs": ["old"]},
            secret_patch=SecretPatch(set={"password": SECRET}),
            environment_key="legacy",
        ),
        "admin",
    )
    await runtime.store.append_audit(
        AuditEntry(
            actor="admin", action="target.create", target_name="mysql-target", summary="created"
        )
    )
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url=BASE,
            cookies={"drpanda_lang": "zh-Hans"},
        ) as client:
            admin_home = await _login(client, "admin", "abcdefgh")
            assert admin_home.headers["location"] == "/"
            overview = await client.get("/")
            assert "<h1>概览</h1>" in overview.text
            assert "可查询的目标" in overview.text
            assert "最近的工具调用" in overview.text
            assert "最近操作" not in overview.text
            assert "1 个目标需要处理" in overview.text
            assert 'href="/admin/overview"' in overview.text
            assert 'href="/targets"' in overview.text

            admin_overview = await client.get("/admin/overview")
            assert admin_overview.status_code == 200
            assert "<h1>管理概览</h1>" in admin_overview.text
            assert "需要处理" in admin_overview.text
            assert f'href="/targets/{created_target.id}/edit"' in admin_overview.text
            assert "最近操作" in admin_overview.text
            assert ">环境</th>" in admin_overview.text

            users = await client.get("/users")
            assert "创建成员" in users.text
            assert users.text.index("最近登录") < users.text.index("是否启用")
            assert 'id="user-drawer"' in users.text
            assert "生成账号" in users.text
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            created = await client.post(
                "/users",
                data={"_csrf": csrf, "username": "ada", "password": ""},
                follow_redirects=False,
            )
            assert created.status_code == 303
            assert "ticket=" in created.headers["location"]
            assert SECRET not in created.headers["location"]
            shown = await client.get(created.headers["location"])
            assert "初始密码只显示这一次" in shown.text
            assert 'class="switch is-on"' in shown.text
            assert 'data-row-action="toggle"' in shown.text
            assert "停用账号" not in shown.text
            assert shown.headers["cache-control"] == "no-store"
            password = _password(shown.text)
            assert len(password) >= 16
            assert f"登录名：ada\n初始密码：{password}" in shown.text
            assert 'data-copy-target="account-handoff"' in shown.text
            with i18n.use_locale("en"):
                assert i18n.t("登录名：") == "Username: "
                assert i18n.t("初始密码：") == "First password: "
            again = await client.get(created.headers["location"])
            assert password not in again.text
            assert "不能再次查看" in again.text

            rows, _total = await runtime.store.list_audit(
                since=datetime(2000, 1, 1, tzinfo=UTC),
                action="user.create",
            )
            assert rows
            assert password not in (rows[0].summary or "")

            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            await client.post("/logout", data={"_csrf": csrf}, follow_redirects=False)

            first = await _login(client, "ada", password)
            assert first.headers["location"] == "/me?tab=password"
            blocked = await client.get("/", follow_redirects=False)
            assert blocked.headers["location"] == "/me?tab=password"
            assert (await client.get("/audit", follow_redirects=False)).headers[
                "location"
            ] == "/me?tab=password"

            await client.get("/me?tab=password")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            changed = await client.post(
                "/me/password",
                data={
                    "_csrf": csrf,
                    "current_password": password,
                    "new_password": "new-password",
                    "confirm_password": "new-password",
                },
                follow_redirects=False,
            )
            assert changed.headers["location"].startswith("/login")

            home = await _login(client, "ada", "new-password")
            assert home.headers["location"] == "/"
            page = await client.get("/")
            assert "可查询的目标" in page.text
            assert "需要处理" not in page.text
            assert "管理概览" not in page.text
            assert 'href="/admin/overview"' not in page.text
            assert 'href="/targets"' in page.text
            assert 'href="/environments"' not in page.text
            assert "系统配置" not in page.text
            assert SECRET not in page.text

            readonly = await client.get("/targets")
            assert readonly.status_code == 200
            assert "mysql-target" in readonly.text
            assert "10.1.1.1" in readonly.text
            assert "允许的库" in readonly.text
            assert "live" in readonly.text
            assert "logs" in readonly.text
            assert "只读" in readonly.text
            assert SECRET not in readonly.text
            for marker in (
                "管理环境",
                "新建目标",
                "新建环境",
                "编辑",
                "删除目标",
                "安装客户端",
                "data-row-action",
            ):
                assert marker not in readonly.text, marker
            for href in ("/targets/new", "/targets/1/edit", "/targets/1/delete"):
                assert href not in readonly.text

            legacy_env = await client.get("/targets", params={"env": "legacy"})
            assert legacy_env.status_code == 200
            assert "legacy-mysql" in legacy_env.text
            assert "10.9.9.9" in legacy_env.text
            assert "已停用" in legacy_env.text

            for path in (
                "/targets/new",
                f"/targets/{created_target.id}/edit",
                f"/targets/{created_target.id}/delete",
                "/admin/overview",
                "/settings",
                "/users",
                "/environments",
            ):
                response = await client.get(path)
                assert response.status_code == 403, path
                assert "没有权限" in response.text
                assert SECRET not in response.text

            csrf = client.cookies.get(auth.CSRF_COOKIE)
            for path in (
                "/targets",
                f"/targets/{created_target.id}/toggle",
                f"/targets/{created_target.id}/test",
                f"/targets/{created_target.id}/delete",
                f"/targets/{created_target.id}/install-client",
            ):
                response = await client.post(path, data={"_csrf": csrf})
                assert response.status_code == 403, path
            json_denied = await client.post(
                "/targets", data={"_csrf": csrf}, headers={"Accept": "application/json"}
            )
            assert json_denied.status_code == 403
            assert json_denied.json()["code"] == "FORBIDDEN"

            audit = await client.get("/audit")
            assert 'value="tool.call" selected' in audit.text
            assert "mysql-target" not in audit.text
            widened = await client.get("/audit?action=all&actor=admin")
            assert "mysql-target" not in widened.text
            assert "ada" in widened.text

            await runtime.store.append_audit(
                AuditEntry(
                    actor="ada",
                    action="tool.call",
                    target_name="mysql-target",
                    summary=(
                        "client=cursor prefix=x mysql_query env=default "
                        'target=mysql-target params={"sql": "SELECT 1"} '
                        "returned=1 elapsed_ms=5 error=-"
                    ),
                    environment_key="default",
                    outcome="ok",
                )
            )
            personal = await client.get("/")
            assert ">环境</th>" in personal.text
            assert "Default" in personal.text
            assert "mysql-target" in personal.text

            ada = await auth.get_user_by_username(runtime.session_factory, "ada")
            assert ada is not None
            token = auth.generate_token()
            await auth.create_mcp_token(
                runtime.session_factory,
                ada.id,
                name="ada",
                token_hash=auth.hash_token(token),
                token_prefix=token[:12],
            )
            principal = await auth.authenticate_mcp_token(
                runtime.session_factory, auth.hash_token(token)
            )
            assert principal is not None
            await auth.set_user_enabled(runtime.session_factory, ada.id, False)
            assert (
                await auth.authenticate_mcp_token(runtime.session_factory, auth.hash_token(token))
                is None
            )
            rejected = await _login(client, "ada", "new-password")
            assert rejected.status_code == 401
    finally:
        await runtime.close()


def _password(html: str) -> str:
    start = html.find('id="initial-password">')
    assert start > 0
    start += len('id="initial-password">')
    end = html.find("</pre>", start)
    return html[start:end].strip()
