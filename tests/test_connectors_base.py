from __future__ import annotations

import asyncio

import httpx
import pytest

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from tests.fakes import make_target


def test_build_envelope_has_eleven_keys() -> None:
    target = make_target()
    envelope = base.build_envelope(
        target,
        summary="SELECT 1",
        elapsed_ms=12,
        rows=[{"a": 1}],
        stats={"x": 1},
        time_range=None,
        notes=["测试"],
    )

    assert set(envelope) == {
        "target",
        "type",
        "summary",
        "time_range",
        "returned",
        "truncated",
        "truncation",
        "elapsed_ms",
        "rows",
        "stats",
        "notes",
    }
    assert envelope["target"] == target.name
    assert envelope["returned"] == 1
    assert envelope["truncated"] is False
    assert envelope["truncation"] is None


def test_apply_row_limits_by_rows() -> None:
    rows, truncation = base.apply_row_limits([{"a": i} for i in range(5)], 2, 1024)

    assert len(rows) == 2
    assert truncation is not None and truncation.reason == "rows"


def test_apply_row_limits_by_bytes() -> None:
    rows, truncation = base.apply_row_limits(
        [{"a": "x" * 100} for _ in range(10)], 100, 150
    )

    assert len(rows) == 1
    assert truncation is not None and truncation.reason == "bytes"


def test_apply_row_limits_not_truncated() -> None:
    rows, truncation = base.apply_row_limits([{"a": 1}], 100, 1024)

    assert len(rows) == 1
    assert truncation is None


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, 15.0),
        ({"timeout_s": "30"}, 30.0),
        ({"timeout_s": "0"}, 1.0),
        ({"timeout_s": "999"}, 120.0),
        ({"timeout_s": "abc"}, 15.0),
    ],
)
def test_timeout_seconds(options: dict, expected: float) -> None:
    target = make_target(options=options)

    assert base.timeout_seconds(target) == expected


@pytest.mark.parametrize(
    ("options", "expected"),
    [({}, 100), ({"max_rows": "10"}, 10), ({"max_rows": "0"}, 1), ({"max_rows": "99999"}, 1000)],
)
def test_max_rows(options: dict, expected: int) -> None:
    assert base.max_rows(make_target(options=options)) == expected


async def test_run_with_timeout_success() -> None:
    async def work() -> str:
        await asyncio.sleep(0)
        return "ok"

    assert await base.run_with_timeout(work(), 1.0) == "ok"


async def test_run_with_timeout_maps_to_upstream_timeout() -> None:
    async def slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(errors.UpstreamTimeout):
        await base.run_with_timeout(slow(), 0.01)


def test_check_http_response_mapping() -> None:
    base.check_http_response(httpx.Response(200), "es")

    with pytest.raises(errors.UpstreamNotFound):
        base.check_http_response(httpx.Response(404), "es")
    with pytest.raises(errors.UpstreamUnavailable):
        base.check_http_response(httpx.Response(500), "es")
    with pytest.raises(errors.UpstreamUnavailable):
        base.check_http_response(httpx.Response(401), "es")


def test_stopwatch_elapsed() -> None:
    with base.Stopwatch() as watch:
        pass

    assert watch.elapsed_ms >= 0


def test_tls_context_requires_cert_and_key_together() -> None:
    with pytest.raises(errors.UpstreamUnavailable):
        base.build_tls_context(
            client_cert="-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----"
        )


def test_tls_context_rejects_invalid_ca() -> None:
    with pytest.raises(errors.UpstreamUnavailable):
        base.build_tls_context(ca_pem="not a pem certificate")


async def test_stream_http_rejects_oversize_response() -> None:
    import httpx

    from dr_panda_mcp import errors
    from dr_panda_mcp.connectors import base as connector_base

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 100)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(errors.UpstreamUnavailable):
            await connector_base.stream_http(
                client, "GET", "http://example.test/", component="test", limit=10
            )


async def test_stream_http_can_truncate_file_content() -> None:
    import httpx

    from dr_panda_mcp.connectors import base as connector_base

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 100)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response, cut = await connector_base.stream_http(
            client,
            "GET",
            "http://example.test/",
            component="test",
            limit=10,
            truncate=True,
        )
    assert cut is True
    assert response.content == b"x" * 10
