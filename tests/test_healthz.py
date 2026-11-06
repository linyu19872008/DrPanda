from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.server import create_app


async def _get(
    runtime: Runtime, path: str = "/healthz", headers: dict[str, str] | None = None
) -> httpx.Response:
    app = create_app(runtime.config, runtime, auth_required=False)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        return await client.get(path, headers=headers)


async def test_healthz_ok(runtime: Runtime) -> None:
    response = await _get(runtime)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert body["version"]


async def test_healthz_reports_db_failure(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(runtime.store, "ping", boom)
    response = await _get(runtime)

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["db"] == "error"


async def test_healthz_rejects_foreign_host(runtime: Runtime) -> None:
    response = await _get(runtime, headers={"host": "evil.example"})

    assert response.status_code == 421


async def test_healthz_rejects_cross_site_origin(runtime: Runtime) -> None:
    response = await _get(runtime, headers={"origin": "http://evil.example"})

    assert response.status_code == 403


async def test_healthz_allows_same_origin(runtime: Runtime) -> None:
    response = await _get(runtime, headers={"origin": "http://127.0.0.1"})

    assert response.status_code == 200


def test_mcp_route_mounted(runtime: Runtime) -> None:
    app = create_app(runtime.config, runtime, auth_required=False)
    inner = app
    while not hasattr(inner, "routes") and hasattr(inner, "app"):
        inner = inner.app
    paths = {getattr(route, "path", None) for route in inner.routes}
    assert "/mcp" in paths
