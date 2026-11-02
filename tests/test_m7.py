from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from dr_panda_mcp import auth
from dr_panda_mcp.config import Config
from dr_panda_mcp.install import load_install_state, save_install_state
from dr_panda_mcp.runtime import Runtime, create_runtime
from dr_panda_mcp.server import create_app
from dr_panda_mcp.setup import SetupApp
from dr_panda_mcp.store.models import AuditRow, UserRow
from dr_panda_mcp.store.protocol import TargetDraft

BASE = "http://127.0.0.1"


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


async def test_setup_wizard_creates_admin_and_install_state(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    app = SetupApp(cfg)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        assert (await client.get("/")).status_code == 303
        page = await client.get("/setup/admin")
        assert page.status_code == 200
        csrf = client.cookies.get(auth.CSRF_COOKIE)
        bad = await client.post(
            "/setup/admin",
            data={"_csrf": csrf, "password": "short", "confirm": "short"},
        )
        assert bad.status_code == 400

        csrf = client.cookies.get(auth.CSRF_COOKIE)
        response = await client.post(
            "/setup/admin",
            data={"_csrf": csrf, "password": "abcdefgh", "confirm": "abcdefgh"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        initial = await client.get("/setup/database")
        assert initial.status_code == 200
        assert 'value="finish" disabled' in initial.text

        csrf = client.cookies.get(auth.CSRF_COOKIE)
        tested = await client.post(
            "/setup/database",
            data={
                "_csrf": csrf,
                "db_type": "sqlite",
                "sqlite_path": str(cfg.database_url.split("///")[-1]),
                "action": "test",
            },
        )
        assert tested.status_code == 200
        assert 'value="finish" disabled' not in tested.text
        assert 'value="finish"' in tested.text

        csrf = client.cookies.get(auth.CSRF_COOKIE)
        finished = await client.post(
            "/setup/database",
            data={
                "_csrf": csrf,
                "db_type": "sqlite",
                "sqlite_path": str(cfg.database_url.split("///")[-1]),
                "action": "finish",
            },
        )
        assert finished.status_code == 200
        assert "MCP token" in finished.text
        home = await client.get("/")
        assert home.status_code == 200
        assert "Targets" in home.text

    async with app.runtime.session_factory() as session:  # type: ignore[union-attr]
        user = await session.scalar(select(UserRow).where(UserRow.username == "admin"))
    assert user is not None
    assert user.role == "admin"
    assert auth.verify_password("abcdefgh", user.password_hash)
    assert load_install_state(cfg.install_file, cfg.install_key_file) is not None
    await app.close()


async def _auth_runtime(tmp_path: Path) -> tuple[Runtime, Config, bytes, str]:
    cfg = _config(tmp_path)
    runtime = await create_runtime(cfg, key_file=tmp_path / "secret.key")
    token = auth.generate_token()
    user = await auth.create_admin(
        runtime.session_factory,
        password_hash=auth.hash_password("abcdefgh"),
    )
    await auth.create_mcp_token(
        runtime.session_factory,
        user.id,
        name="默认 Token",
        token_hash=auth.hash_token(token),
        token_prefix=token[:12],
    )
    key = auth.load_or_create_session_key(cfg.session_key_file)
    return runtime, cfg, key, token


async def test_login_session_csrf_and_actor(tmp_path: Path) -> None:
    runtime, cfg, key, _token = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            unauth = await client.get("/", follow_redirects=False)
            assert unauth.status_code == 303
            assert unauth.headers["location"].startswith("/login?next=")
            assert (await client.get("/mcp")).status_code == 401

            login = await client.get("/login")
            assert login.status_code == 200
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            bad = await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "wrong"},
            )
            assert bad.status_code == 401

            csrf = client.cookies.get(auth.CSRF_COOKIE)
            good = await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )
            assert good.status_code == 303
            assert auth.SESSION_COOKIE in client.cookies

            home = await client.get("/")
            assert home.status_code == 200
            assert "Targets" in home.text

            missing_csrf = await client.post("/targets", data={"name": "x"})
            assert missing_csrf.status_code == 403

            csrf = client.cookies.get(auth.CSRF_COOKIE)
            saved = await client.post(
                "/settings",
                data={
                    "_csrf": csrf,
                    "audit_retention_days": "30",
                    "target_max_concurrency": "10",
                },
            )
            assert saved.status_code == 303
            async with runtime.session_factory() as session:
                actor = await session.scalar(
                    select(AuditRow.actor)
                    .where(AuditRow.action == "settings.update")
                    .order_by(AuditRow.id.desc())
                )
            assert actor == "admin"

            mcp_bad = await client.get("/mcp", headers={"Authorization": "Bearer bad"})
            assert mcp_bad.status_code == 401
            assert "WWW-Authenticate" in mcp_bad.headers
    finally:
        await runtime.close()

    # actor 通过认证上下文写入；本用例覆盖认证门与 CSRF，审计 actor 由现有 store 测试覆盖。


async def test_session_ttl_setting_controls_login_cookie(tmp_path: Path) -> None:
    runtime, cfg, key, _ = await _auth_runtime(tmp_path)
    await runtime.store.update_settings({"session_ttl_minutes": "5"}, "admin")
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            response = await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )
        assert "Max-Age=300" in response.headers["set-cookie"]
    finally:
        await runtime.close()


async def test_mcp_token_lookup(tmp_path: Path) -> None:
    runtime, _cfg, _key, token = await _auth_runtime(tmp_path)
    try:
        principal = await auth.authenticate_mcp_token(
            runtime.session_factory, auth.hash_token(token)
        )
        assert principal is not None and principal.user.username == "admin"
        assert (
            await auth.authenticate_mcp_token(runtime.session_factory, "nope") is None
        )
    finally:
        await runtime.close()


async def test_install_state_is_encrypted(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    save_install_state(
        cfg.install_file,
        cfg.install_key_file,
        "sqlite+aiosqlite:///secret-password.db",
    )
    raw = cfg.install_file.read_text(encoding="utf-8")
    assert "secret-password.db" not in raw
    state = load_install_state(cfg.install_file, cfg.install_key_file)
    assert state is not None
    assert state.database_url.endswith("secret-password.db")


async def test_mcp_bearer_initializes_with_auth(tmp_path: Path) -> None:
    runtime, cfg, key, token = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    inner = app.app.app  # CSRF -> Auth -> FastMCP
    try:
        async with (
            inner.router.lifespan_context(inner),
            httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client,
        ):
            response = await client.post(
                    "/mcp",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    },
                )
        assert response.status_code == 200
        assert "serverInfo" in response.text
    finally:
        await runtime.close()


async def test_logout_clears_session(tmp_path: Path) -> None:
    runtime, cfg, key, _ = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            logout = await client.post(
                "/logout", data={"_csrf": csrf}, follow_redirects=False
            )
            assert logout.status_code == 303
            after = await client.get("/", follow_redirects=False)
            assert after.status_code == 303
    finally:
        await runtime.close()


async def test_setup_existing_database_keeps_targets(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runtime = await create_runtime(cfg, key_file=tmp_path / "secret.key")
    try:
        await runtime.store.create(
            TargetDraft(
                name="existing-target",
                type="mysql",
                enabled=True,
                options={"host": "127.0.0.1"},
            ),
            "anonymous",
        )
    finally:
        await runtime.close()

    app = SetupApp(cfg)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        await client.get("/setup/admin")
        csrf = client.cookies.get(auth.CSRF_COOKIE)
        await client.post(
            "/setup/admin",
            data={"_csrf": csrf, "password": "abcdefgh", "confirm": "abcdefgh"},
        )
        csrf = client.cookies.get(auth.CSRF_COOKIE)
        await client.post(
            "/setup/database",
            data={
                "_csrf": csrf,
                "db_type": "sqlite",
                "sqlite_path": str(tmp_path / "db.sqlite"),
                "action": "test",
            },
        )
        csrf = client.cookies.get(auth.CSRF_COOKIE)
        await client.post(
            "/setup/database",
            data={
                "_csrf": csrf,
                "db_type": "sqlite",
                "sqlite_path": str(tmp_path / "db.sqlite"),
                "action": "finish",
            },
        )
    assert app.runtime is not None
    target = await app.runtime.store.get("existing-target")
    assert target is not None
    async with app.runtime.session_factory() as session:
        admin = await session.scalar(select(UserRow).where(UserRow.username == "admin"))
    assert admin is not None
    await app.close()


async def test_my_page_tokens_and_password_change(tmp_path: Path) -> None:
    runtime, cfg, key, old_token = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )

            me = await client.get("/me")
            assert me.status_code == 200
            assert "http://127.0.0.1:8111/mcp" in me.text
            assert old_token[:12] in me.text
            assert old_token not in me.text

            # 创建第二个 Token；名称可选
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            created = await client.post(
                "/me/tokens",
                data={"_csrf": csrf, "name": "Cursor"},
            )
            assert created.status_code == 200
            assert 'id="copy-mcp-token"' in created.text
            assert 'src="/static/copy-token.js' in created.text
            assert 'id="token-create"' in created.text
            assert 'data-open-on-load="true"' in created.text
            assert "无 JS 时可点击 Token 全选" in created.text or "Without JS, click the token" in created.text
            import re
            match = re.search(r'<pre id="mcp-token-value" class="mono setup-secret">([^<]+)</pre>', created.text)
            assert match is not None
            new_token = match.group(1).strip()
            assert new_token != old_token

            # 旧 Token 仍在；新 Token 可用
            assert (
                await auth.authenticate_mcp_token(
                    runtime.session_factory, auth.hash_token(old_token)
                )
                is not None
            )
            assert (
                await auth.authenticate_mcp_token(
                    runtime.session_factory, auth.hash_token(new_token)
                )
                is not None
            )

            # 物理删除旧 Token；删除不要求当前密码
            old_tokens = await auth.list_mcp_tokens(
                runtime.session_factory, 1, offset=0, limit=20
            )
            old_row = next((item for item in old_tokens if item.token_prefix == old_token[:12]), None)
            assert old_row is not None
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            deleted = await client.post(
                f"/me/tokens/{old_row.id}/delete",
                data={"_csrf": csrf},
                follow_redirects=False,
            )
            assert deleted.status_code == 303
            assert deleted.headers["location"] == "/me?deleted=1"
            after_delete = await client.get("/me?deleted=1")
            assert "Token deleted" in after_delete.text
            assert (
                await auth.authenticate_mcp_token(
                    runtime.session_factory, auth.hash_token(old_token)
                )
                is None
            )
            assert (
                await auth.authenticate_mcp_token(
                    runtime.session_factory, auth.hash_token(new_token)
                )
                is not None
            )

            csrf = client.cookies.get(auth.CSRF_COOKIE)
            bad_pw = await client.post(
                "/me/password",
                data={
                    "_csrf": csrf,
                    "current_password": "abcdefgh",
                    "new_password": "newpass88",
                    "confirm_password": "mismatch",
                },
            )
            assert bad_pw.status_code == 400

            csrf = client.cookies.get(auth.CSRF_COOKIE)
            changed = await client.post(
                "/me/password",
                data={
                    "_csrf": csrf,
                    "current_password": "abcdefgh",
                    "new_password": "newpass88",
                    "confirm_password": "newpass88",
                },
                follow_redirects=False,
            )
            assert changed.status_code == 303
            assert changed.headers["location"].startswith("/login")

            after = await client.get("/", follow_redirects=False)
            assert after.status_code == 303

            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            old_login = await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
            )
            assert old_login.status_code == 401
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            new_login = await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "newpass88"},
                follow_redirects=False,
            )
            assert new_login.status_code == 303
    finally:
        await runtime.close()


async def test_token_list_pagination(tmp_path: Path) -> None:
    runtime, cfg, key, _ = await _auth_runtime(tmp_path)
    try:
        user = await auth.get_user_by_username(runtime.session_factory, "admin")
        assert user is not None
        for index in range(25):
            token = auth.generate_token()
            await auth.create_mcp_token(
                runtime.session_factory,
                user.id,
                name=f"token-{index}",
                token_hash=auth.hash_token(token),
                token_prefix=token[:12],
            )
        app = create_app(cfg, runtime, auth_required=True, session_key=key)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url=BASE,
            cookies={"drpanda_lang": "zh-Hans"},
        ) as client:
            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )
            first = await client.get("/me")
            second = await client.get("/me?page=2")
        assert "第 1 / 2 页" in first.text
        assert "第 2 / 2 页" in second.text
        assert "共 26 个" in first.text
    finally:
        await runtime.close()


async def test_me_forms_accept_same_origin_header(tmp_path: Path) -> None:
    runtime, cfg, key, _ = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )
            me = await client.get("/me")
            assert me.headers["referrer-policy"] == "same-origin"

            csrf = client.cookies.get(auth.CSRF_COOKIE)
            created = await client.post(
                "/me/tokens",
                headers={"Origin": BASE},
                data={"_csrf": csrf, "name": "origin-test"},
                follow_redirects=False,
            )
        assert created.status_code == 200
        assert "origin-test" in created.text
    finally:
        await runtime.close()


async def test_copy_token_script_is_served(tmp_path: Path) -> None:
    runtime, cfg, key, _ = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            response = await client.get("/static/copy-token.js")
        assert response.status_code == 200
        assert "navigator.clipboard" in response.text
        assert "copy-mcp-token" in response.text
    finally:
        await runtime.close()


async def test_me_uses_dialog_with_no_js_fallbacks(tmp_path: Path) -> None:
    runtime, cfg, key, _ = await _auth_runtime(tmp_path)
    app = create_app(cfg, runtime, auth_required=True, session_key=key)
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            await client.get("/login")
            csrf = client.cookies.get(auth.CSRF_COOKIE)
            await client.post(
                "/login",
                data={"_csrf": csrf, "username": "admin", "password": "abcdefgh"},
                follow_redirects=False,
            )
            me = await client.get("/me")
            new_page = await client.get("/me/tokens/new")
            script = await client.get("/static/app.js")

        assert me.status_code == 200
        assert 'data-dialog-open="token-create"' in me.text
        assert '<dialog id="token-create"' in me.text
        assert 'href="/me/tokens/new"' in me.text
        assert 'src="/static/app.js' in me.text
        assert new_page.status_code == 200
        assert "<script" not in new_page.text
        assert script.status_code == 200
        assert "showModal" in script.text
    finally:
        await runtime.close()
