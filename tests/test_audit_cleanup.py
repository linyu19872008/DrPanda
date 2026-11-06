from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from dr_panda_mcp import audit, settings
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.models import AuditRow


async def _insert_audit(runtime: Runtime, action: str, *, days_ago: float) -> None:
    created = datetime.now(UTC) - timedelta(days=days_ago)
    async with runtime.session_factory() as session, session.begin():
        session.add(
            AuditRow(
                created_at=created,
                actor="anonymous",
                action=action,
                target_name=None,
                summary="test",
            )
        )


async def _actions(runtime: Runtime) -> list[str]:
    async with runtime.session_factory() as session:
        rows = await session.execute(select(AuditRow.action).order_by(AuditRow.id))
    return [row[0] for row in rows.all()]


async def test_cleanup_deletes_expired_and_keeps_recent(runtime: Runtime) -> None:
    await _insert_audit(runtime, "old.one", days_ago=100)
    await _insert_audit(runtime, "old.two", days_ago=91)
    await _insert_audit(runtime, "recent", days_ago=10)

    deleted = await audit.cleanup_once(runtime)

    assert deleted == 2
    assert await _actions(runtime) == ["recent"]


async def test_cleanup_boundary_keeps_inside_retention(runtime: Runtime) -> None:
    await _insert_audit(runtime, "inside", days_ago=89)
    await _insert_audit(runtime, "outside", days_ago=90.1)

    deleted = await audit.cleanup_once(runtime)

    assert deleted == 1
    assert await _actions(runtime) == ["inside"]


async def test_cleanup_uses_current_setting(runtime: Runtime) -> None:
    await settings.update(runtime.store, {"audit_retention_days": "30"}, "anonymous")
    await _insert_audit(runtime, "too.old", days_ago=40)
    await _insert_audit(runtime, "recent", days_ago=20)

    deleted = await audit.cleanup_once(runtime)

    assert deleted == 1
    actions = await _actions(runtime)
    assert "too.old" not in actions
    assert "recent" in actions


async def test_cleanup_interval_shrinks_within_one_slice(monkeypatch) -> None:
    from dr_panda_mcp.store.protocol import Settings

    clock = {"now": 0.0}
    sleeps: list[float] = []
    calls = {"n": 0}

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    async def fake_load(_store) -> Settings:
        calls["n"] += 1
        minutes = 60 if calls["n"] == 1 else 5
        return Settings(
            audit_retention_days=90,
            target_max_concurrency=10,
            audit_cleanup_interval_minutes=minutes,
        )

    monkeypatch.setattr(audit, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    monkeypatch.setattr(audit.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(audit.settings_module, "load", fake_load)

    await audit._sleep_with_configured_interval(SimpleNamespace(store=None))

    # 初始 60 分钟；第一次分片后读到 5 分钟，应在一分钟内按新值结束。
    assert sleeps == [60.0, 60.0, 60.0, 60.0, 60.0]
    assert clock["now"] == 300.0


async def test_cleanup_uses_configured_batch_and_deadline(
    runtime: Runtime, monkeypatch
) -> None:
    await settings.update(
        runtime.store,
        {"audit_cleanup_batch_size": "200", "audit_cleanup_max_seconds": "45"},
        "anonymous",
    )
    captured: dict[str, object] = {}

    async def fake_cleanup(
        retention_days: int, *, batch_size: int = 1000, max_seconds: float = 300.0
    ) -> int:
        captured.update(
            retention_days=retention_days,
            batch_size=batch_size,
            max_seconds=max_seconds,
        )
        return 0

    monkeypatch.setattr(runtime.store, "cleanup_audit", fake_cleanup)
    await audit.cleanup_once(runtime)

    assert captured == {
        "retention_days": 90,
        "batch_size": 200,
        "max_seconds": 45.0,
    }


async def test_cleanup_in_batches(runtime: Runtime) -> None:
    for index in range(5):
        await _insert_audit(runtime, f"old.{index}", days_ago=120)

    deleted = await runtime.store.cleanup_audit(90, batch_size=2)

    assert deleted == 5
    assert await runtime.store.cleanup_audit(90) == 0


async def test_cleanup_does_not_write_audit(runtime: Runtime) -> None:
    await _insert_audit(runtime, "old.one", days_ago=120)
    before = await _actions(runtime)

    await audit.cleanup_once(runtime)

    after = await _actions(runtime)
    assert before == ["old.one"]
    assert after == []
    assert "audit.cleanup" not in after
