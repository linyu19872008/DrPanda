"""M2 测试用的目标/连接器替身。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from dr_panda_mcp.guards.protocol import Decision, allow
from dr_panda_mcp.store.protocol import Target


def make_target(
    *,
    target_id: int = 1,
    type_: str = "mysql",
    name: str | None = None,
    options: dict[str, Any] | None = None,
    secret: dict[str, str] | None = None,
    secret_ok: bool = True,
    secret_fields: frozenset[str] | None = None,
    updated_at: datetime | None = None,
    enabled: bool = True,
) -> Target:
    now = datetime.now(UTC)
    fields = (
        secret_fields
        if secret_fields is not None
        else frozenset((secret or {}).keys())
    )
    return Target(
        id=target_id,
        type=type_,
        name=name or f"{type_}-1",
        enabled=enabled,
        options=options if options is not None else {"host": "127.0.0.1"},
        secret=secret or {},
        secret_fields=fields,
        secret_ok=secret_ok,
        created_at=now,
        updated_at=updated_at or now,
        last_test_at=None,
        last_test_ok=None,
        last_test_error=None,
    )


class FakeStore:
    def __init__(self, targets: list[Target]) -> None:
        self._targets = {target.name: target for target in targets}

    async def get(self, name: str) -> Target | None:
        return self._targets.get(name)

    async def get_settings(self) -> dict[str, str]:
        return {"audit_retention_days": "90", "target_max_concurrency": "10"}

    async def list_settings_changes(self, limit: int = 5):
        return []


class FakeConnector:
    def __init__(
        self,
        name: str = "mysql",
        *,
        decision: Decision | None = None,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self._decision = decision or allow()
        self.delay = delay
        self.created = 0
        self.closed = 0
        self.probes = 0
        self.active = 0
        self.max_active = 0

    def probe_guard(self) -> Decision:
        return self._decision

    def create_client(self, target: Target) -> dict[str, Any]:
        self.created += 1
        return {"client_id": self.created, "target": target.name}

    async def probe(self, client: dict[str, Any], target: Target) -> None:
        self.probes += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        finally:
            self.active -= 1

    async def close_client(self, client: dict[str, Any]) -> None:
        self.closed += 1
