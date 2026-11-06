from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from dr_panda_mcp import errors
from dr_panda_mcp.catalog import Catalog
from dr_panda_mcp.guards.protocol import dangerous, guard_rejected
from dr_panda_mcp.store.protocol import Settings
from tests.fakes import FakeConnector, FakeStore, make_target


def _store(target) -> FakeStore:
    return FakeStore([target])


async def _loader_with_limit(limit: int) -> callable:
    async def loader(_store) -> Settings:
        return Settings(audit_retention_days=90, target_max_concurrency=limit)

    return loader


async def test_resolve_not_found() -> None:
    catalog = Catalog(FakeStore([]))

    with pytest.raises(errors.TargetNotFound):
        await catalog.resolve("missing")


async def test_resolve_disabled() -> None:
    target = make_target(enabled=False)
    catalog = Catalog(_store(target))

    with pytest.raises(errors.TargetDisabled):
        await catalog.resolve(target.name)


async def test_resolve_type_mismatch() -> None:
    target = make_target(type_="mysql")
    catalog = Catalog(_store(target))

    with pytest.raises(errors.TargetTypeMismatch):
        await catalog.resolve(target.name, expected_type="redis")


async def test_resolve_secret_unavailable() -> None:
    target = make_target(secret={"password": "x"}, secret_ok=False)
    catalog = Catalog(_store(target))

    with pytest.raises(errors.SecretUnavailable):
        await catalog.resolve(target.name)


async def test_test_connection_success() -> None:
    target = make_target()
    catalog = Catalog(_store(target))
    connector = FakeConnector()

    await catalog.test_connection(target.name, connector)

    assert connector.created == 1
    assert connector.probes == 1
    await catalog.close()


async def test_test_connection_guard_rejection_has_no_outbound() -> None:
    target = make_target()
    catalog = Catalog(_store(target))
    connector = FakeConnector(decision=guard_rejected("test.reject", "拒绝"))

    with pytest.raises(errors.GuardRejected) as excinfo:
        await catalog.test_connection(target.name, connector)

    assert excinfo.value.code == errors.GUARD_REJECTED
    assert connector.created == 0
    assert connector.probes == 0


async def test_test_connection_dangerous_has_no_outbound() -> None:
    target = make_target()
    catalog = Catalog(_store(target))
    connector = FakeConnector(decision=dangerous("test.danger", "危险"))

    with pytest.raises(errors.GuardRejected) as excinfo:
        await catalog.test_connection(target.name, connector)

    assert excinfo.value.code == errors.DANGEROUS_OPERATION
    assert connector.created == 0


async def test_client_pool_reused_then_invalidated() -> None:
    target = make_target()
    catalog = Catalog(_store(target))
    connector = FakeConnector()

    await catalog.test_connection(target.name, connector)
    await catalog.test_connection(target.name, connector)
    assert connector.created == 1
    assert connector.closed == 0

    newer = make_target(updated_at=datetime.now(UTC) + timedelta(seconds=1))
    store = FakeStore([newer])
    catalog = Catalog(store)
    first = FakeConnector()
    await catalog.test_connection(newer.name, first)
    newer_later = make_target(
        updated_at=datetime.now(UTC) + timedelta(seconds=5)
    )
    catalog._store = FakeStore([newer_later])
    await catalog.test_connection(newer_later.name, first)

    assert first.created == 2
    assert first.closed == 1
    await catalog.close()


async def test_concurrency_limit_from_settings() -> None:
    target = make_target()
    catalog = Catalog(_store(target), settings_loader=await _loader_with_limit(10))
    connector = FakeConnector(delay=0.03)

    await asyncio.gather(
        *[catalog.test_connection(target.name, connector) for _ in range(11)]
    )

    assert connector.max_active <= 10
    assert connector.max_active >= 2


async def test_concurrency_limit_can_be_tightened() -> None:
    target = make_target()
    catalog = Catalog(_store(target), settings_loader=await _loader_with_limit(2))
    connector = FakeConnector(delay=0.03)

    await asyncio.gather(
        *[catalog.test_connection(target.name, connector) for _ in range(6)]
    )

    assert connector.max_active <= 2


async def test_timeout_maps_to_upstream_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = make_target()
    catalog = Catalog(_store(target))
    connector = FakeConnector(delay=0.2)
    monkeypatch.setattr("dr_panda_mcp.catalog.connectors_base.timeout_seconds", lambda _t: 0.02)

    with pytest.raises(errors.UpstreamTimeout):
        await catalog.test_connection(target.name, connector)


async def test_close_releases_clients() -> None:
    target = make_target()
    catalog = Catalog(_store(target))
    connector = FakeConnector()

    await catalog.test_connection(target.name, connector)
    await catalog.close()

    assert connector.closed == 1


async def test_global_concurrency_limit_from_settings() -> None:
    targets = [
        make_target(target_id=i, name=f"mysql-{i}") for i in range(1, 4)
    ]
    store = FakeStore(targets)

    async def loader(_store) -> Settings:
        return Settings(
            audit_retention_days=90,
            target_max_concurrency=10,
            global_max_concurrent_calls=2,
        )

    catalog = Catalog(store, settings_loader=loader)
    connector = FakeConnector(delay=0.03)
    try:
        await asyncio.gather(
            *[
                catalog.test_connection(target.name, connector)
                for target in targets
                for _ in range(3)
            ]
        )
    finally:
        await catalog.close()

    assert connector.max_active <= 2


async def test_idle_clients_are_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = [
        make_target(target_id=1, name="mysql-1"),
        make_target(target_id=2, name="mysql-2"),
    ]
    store = FakeStore(targets)
    clock = {"now": 1000.0}
    monkeypatch.setattr(
        "dr_panda_mcp.catalog.time.monotonic", lambda: clock["now"]
    )

    async def loader(_store) -> Settings:
        return Settings(
            audit_retention_days=90,
            target_max_concurrency=10,
            catalog_idle_seconds=10,
        )

    catalog = Catalog(store, settings_loader=loader)
    connector = FakeConnector()
    try:
        await catalog.client(targets[0], connector)
        clock["now"] += 11
        await catalog.client(targets[1], connector)
        assert len(catalog._pool) == 1
        assert connector.closed == 1
    finally:
        await catalog.close()


async def test_catalog_evicts_on_cache_hit_when_limit_shrinks() -> None:
    targets = [
        make_target(target_id=i, name=f"mysql-{i}") for i in range(1, 7)
    ]
    store = FakeStore(targets)
    current = {"limit": 6}

    async def loader(_store) -> Settings:
        return Settings(
            audit_retention_days=90,
            target_max_concurrency=10,
            catalog_max_clients=current["limit"],
        )

    catalog = Catalog(store, settings_loader=loader)
    connector = FakeConnector()
    try:
        for target in targets:
            await catalog.client(target, connector)
        assert len(catalog._pool) == 6

        current["limit"] = 4
        # 命中缓存也要按新上限淘汰，而不是等下一次 cache miss。
        await catalog.client(targets[0], connector)
        assert len(catalog._pool) == 4
    finally:
        await catalog.close()


async def test_catalog_evicts_by_configured_client_limit() -> None:
    targets = [
        make_target(target_id=i, name=f"mysql-{i}") for i in range(1, 6)
    ]
    store = FakeStore(targets)

    async def loader(_store) -> Settings:
        return Settings(
            audit_retention_days=90,
            target_max_concurrency=10,
            catalog_max_clients=4,
        )

    catalog = Catalog(store, settings_loader=loader)
    connector = FakeConnector()
    try:
        for target in targets:
            await catalog.client(target, connector)
        assert len(catalog._pool) == 4
    finally:
        await catalog.close()
