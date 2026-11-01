from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
