from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from dr_panda_mcp.connectors.cls import _CLSClient
from dr_panda_mcp.connectors.gitlab import _GitLabClient
from tests.fakes import make_target


def _gitlab_target():
    return make_target(
        type_="gitlab",
        options={
            "base_url": "https://gitlab.example.com",
            "allowed_projects": ["group/app"],
            "timeout_s": "15",
        },
        secret={"token": "tok"},
    )


def _response(path: str, *, json: Any = None, text: str | None = None) -> httpx.Response:
    request = httpx.Request("GET", f"https://gitlab.example.com{path}")
    if json is not None:
        return httpx.Response(200, json=json, request=request)
    return httpx.Response(200, text=text or "", request=request)


async def test_gitlab_search_code_request_and_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _GitLabClient(_gitlab_target())
    calls: list[tuple[str, dict[str, Any] | None]] = []

    async def fake_get(path: str, params: dict[str, Any] | None = None):
        calls.append((path, params))
        return _response(
            path, json=[{"path": "app/main.py", "startline": 3, "data": "boom"}]
        )

    monkeypatch.setattr(client, "_get", fake_get)

    rows = await client.search_code("group/app", "boom", ref="main", per_page=20)

    assert rows == [{"path": "app/main.py", "startline": 3, "data": "boom"}]
    path, params = calls[0]
    assert path.startswith("/api/v4/projects/group%2Fapp/search")
    assert params == {"scope": "blobs", "search": "boom", "per_page": 20, "ref": "main"}


async def test_gitlab_get_file_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _GitLabClient(_gitlab_target())
    calls: list[tuple[str, dict[str, Any] | None]] = []

    async def fake_get(path: str, params: dict[str, Any] | None = None):
        calls.append((path, params))
        return _response(path, text="print('hello')")

    monkeypatch.setattr(client, "_get", fake_get)

    content = await client.get_file("group/app", "app/main.py", ref="main")

    assert content == "print('hello')"
    assert calls[0][0].endswith("/repository/files/app%2Fmain.py/raw")
    assert calls[0][1] == {"ref": "main"}


async def test_gitlab_blame_request_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _GitLabClient(_gitlab_target())
    calls: list[tuple[str, dict[str, Any] | None]] = []

    async def fake_get(path: str, params: dict[str, Any] | None = None):
        calls.append((path, params))
        return _response(
            path,
            json=[{"commit": {"short_id": "abc"}, "lines": ["a", "b"]}],
        )

    monkeypatch.setattr(client, "_get", fake_get)

    rows = await client.blame(
        "group/app", "app/main.py", ref="main", line_from=2, line_to=3
    )

    assert rows[0]["lines"] == ["a", "b"]
    assert calls[0][1] == {"ref": "main", "range[start]": 2, "range[end]": 3}


def _install_fake_cls_sdk(monkeypatch: pytest.MonkeyPatch, response: Any) -> dict:
    state: dict[str, Any] = {}

    class SearchLogRequest:
        pass

    class DescribeLogContextRequest:
        pass

    class DescribeLogsetsRequest:
        pass

    class FakeClsClient:
        def __init__(self, credential, region, timeout) -> None:
            state["region"] = region
            state["timeout"] = timeout

        def SearchLog(self, request):
            state["search_request"] = request
            return response

        def DescribeLogContext(self, request):
            state["context_request"] = request
            return response

        def DescribeLogsets(self, request):
            return response

    credential_module = types.ModuleType("tencentcloud.common.credential")
    credential_module.Credential = lambda sid, skey: SimpleNamespace(
        sid=sid, skey=skey
    )
    common_module = types.ModuleType("tencentcloud.common")
    common_module.credential = credential_module

    models_module = types.ModuleType("tencentcloud.cls.v20201016.models")
    models_module.SearchLogRequest = SearchLogRequest
    models_module.DescribeLogContextRequest = DescribeLogContextRequest
    models_module.DescribeLogsetsRequest = DescribeLogsetsRequest

    cls_client_module = types.ModuleType("tencentcloud.cls.v20201016.cls_client")
    cls_client_module.ClsClient = FakeClsClient

    v20201016 = types.ModuleType("tencentcloud.cls.v20201016")
    v20201016.models = models_module
    v20201016.cls_client = cls_client_module

    cls_package = types.ModuleType("tencentcloud.cls")
    cls_package.v20201016 = v20201016

    tencentcloud = types.ModuleType("tencentcloud")
    tencentcloud.common = common_module
    tencentcloud.cls = cls_package

    for name, module in {
        "tencentcloud": tencentcloud,
        "tencentcloud.common": common_module,
        "tencentcloud.common.credential": credential_module,
        "tencentcloud.cls": cls_package,
        "tencentcloud.cls.v20201016": v20201016,
        "tencentcloud.cls.v20201016.models": models_module,
        "tencentcloud.cls.v20201016.cls_client": cls_client_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return state


async def test_cls_search_log_maps_topic_and_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        Results=[
            SimpleNamespace(Time=1767229200, Log="boom"),
            SimpleNamespace(Time=None, Log="second"),
        ]
    )
    state = _install_fake_cls_sdk(monkeypatch, response)
    target = make_target(
        type_="cls",
        options={
            "region": "ap-guangzhou",
            "allowed_topics": ["logset/app"],
            "timeout_s": "15",
        },
        secret={"secret_id": "sid", "secret_key": "skey"},
    )
    client = _CLSClient(target)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 1, tzinfo=UTC)

    rows = await client.search_log(
        topic="logset/app", query="level:ERROR", start=start, end=end, limit=10
    )

    request = state["search_request"]
    assert request.TopicId == "app"
    assert request.Query == "level:ERROR"
    assert request.Limit == 10
    assert rows[0]["content"] == "boom"
    assert rows[0]["time"] == "2026-01-01T01:00:00+00:00"
    assert rows[1]["time"] is None


async def test_cls_describe_context_maps_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        ContextInfos=[
            SimpleNamespace(Time=1767229200, Log="context line", PkgId="pkg-1")
        ]
    )
    state = _install_fake_cls_sdk(monkeypatch, response)
    target = make_target(
        type_="cls",
        options={"region": "ap-guangzhou", "allowed_topics": ["logset/app"]},
        secret={"secret_id": "sid", "secret_key": "skey"},
    )
    client = _CLSClient(target)

    rows = await client.describe_context(
        topic="logset/app", log_id="pkg-1", before=5, after=5
    )

    assert state["context_request"].PkgId == "pkg-1"
    assert state["context_request"].TopicId == "app"
    assert rows[0]["package_id"] == "pkg-1"
    assert rows[0]["content"] == "context line"
