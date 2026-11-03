from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from httpx import ASGITransport
from sqlalchemy.engine import make_url

from dr_panda_mcp.catalog import Catalog
from dr_panda_mcp.errors import (
    EnvironmentDisabled,
    EnvironmentKeyTaken,
    EnvironmentNotEmpty,
    EnvironmentRequired,
)
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app, create_server
from dr_panda_mcp.store.protocol import SecretPatch, TargetDraft


def _draft(name: str, environment_key: str, password: str) -> TargetDraft:
    return TargetDraft(
        name=name,
        type="mysql",
        enabled=True,
        options={"host": "127.0.0.1"},
        secret_patch=SecretPatch(set={"password": password}),
        environment_key=environment_key,
    )


def _client(runtime: Runtime) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(
            app=create_app(runtime.config, runtime, auth_required=False)
        ),
        base_url="http://127.0.0.1",
        cookies={"drpanda_lang": "zh-Hans"},
    )


def _db_path(runtime: Runtime) -> Path:
    return Path(make_url(str(runtime.engine.url)).database)


async def test_same_name_is_isolated_by_environment(runtime: Runtime) -> None:
    await runtime.store.create_environment("lechang-prod", "乐畅生产", "anonymous")
    await runtime.store.create_environment("test", "测试", "anonymous")
    await runtime.store.create(
        _draft("order-mysql", "lechang-prod", "prod-secret"), "anonymous"
    )
    await runtime.store.create(_draft("order-mysql", "test", "test-secret"), "anonymous")

    prod = await runtime.store.get("order-mysql", environment="lechang-prod")
    test = await runtime.store.get("order-mysql", environment="test")
    assert prod is not None and test is not None
    assert prod.id != test.id
    assert prod.secret["password"] == "prod-secret"
    assert test.secret["password"] == "test-secret"
    assert prod.environment_title == "乐畅生产"

    with pytest.raises(EnvironmentRequired):
        await runtime.store.get("order-mysql")

    with sqlite3.connect(_db_path(runtime)) as connection:
        rows = connection.execute("SELECT secret_json FROM targets").fetchall()
    assert rows
    assert json.loads(rows[0][0])["password"]["v"] == 2


async def test_duplicate_key_and_nonempty_delete(runtime: Runtime) -> None:
    created = await runtime.store.create_environment("test", "测试", "anonymous")
    with pytest.raises(EnvironmentKeyTaken):
        await runtime.store.create_environment("test", "另一个测试", "anonymous")

    await runtime.store.create(_draft("order-mysql", "test", "pw"), "anonymous")
    with pytest.raises(EnvironmentNotEmpty):
        await runtime.store.delete_environment(created.id, "anonymous")

    await runtime.store.update_environment(
        created.id, title="测试环境", enabled=False, actor="anonymous"
    )
    with pytest.raises(EnvironmentDisabled):
        await Catalog(runtime.store).resolve("order-mysql", environment="test")


async def test_systems_status_lists_environments_then_targets(runtime: Runtime) -> None:
    await runtime.store.create_environment("lechang-prod", "乐畅生产", "anonymous")
    await runtime.store.create(
        _draft("order-mysql", "lechang-prod", "pw"), "anonymous"
    )
    server = create_server(runtime.config, runtime)

    async with Client(server) as client:
        listed = await client.call_tool("systems_status", {})
        scoped = await client.call_tool(
            "systems_status", {"environment": "lechang-prod"}
        )
        with pytest.raises(ToolError) as missing:
            await client.call_tool("systems_status", {"environment": "nope"})
        with pytest.raises(ToolError) as required:
            await client.call_tool("mysql_tables", {"target": "order-mysql"})

    overview = listed.structured_content
    assert overview is not None
    assert {row["key"] for row in overview["rows"]} == {"default", "lechang-prod"}
    detail = scoped.structured_content
    assert detail is not None
    assert [row["name"] for row in detail["rows"]] == ["order-mysql"]
    assert "ENVIRONMENT_NOT_FOUND" in str(missing.value)
    assert "ENVIRONMENT_REQUIRED" in str(required.value)


async def test_web_environment_flow_stays_in_the_chosen_environment(
    runtime: Runtime,
) -> None:
    async with _client(runtime) as client:
        home = await client.get("/")
        form = await client.get("/environments/new")
        created = await client.post(
            "/environments",
            data={"title": "乐畅生产", "key": "lechang-prod", "enabled": "on"},
        )
        landed = await client.get(created.headers["location"])
        chooser = await client.get("/targets/new", params={"env": "lechang-prod"})
        target_form = await client.get(
            "/targets/new", params={"type": "mysql", "env": "lechang-prod"}
        )
        await runtime.store.create(_draft("order-mysql", "default", "pw"), "anonymous")
        environments = await client.get("/environments")
        blocked = await client.post("/environments/1/delete")

    assert "管理环境" in home.text
    assert "调用标识" in form.text
    assert 'placeholder="prod"' in form.text
    assert created.status_code == 303
    assert "flash=env_created" in created.headers["location"]
    assert "env=lechang-prod" in created.headers["location"]
    assert "环境已创建" in landed.text
    assert "这个环境还没有目标" in landed.text
    assert "乐畅生产" in chooser.text
    assert "lechang-prod" in chooser.text
    assert 'value="lechang-prod" selected' in target_form.text
    assert "保存后不能更换" in target_form.text
    assert "有目标时不能删除" in environments.text
    assert blocked.status_code == 400
    assert "还不能删除这个环境" in blocked.text
