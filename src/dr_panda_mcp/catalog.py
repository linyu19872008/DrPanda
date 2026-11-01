"""排查目标目录：按 name 读取、状态校验、连接池与并发（planning 5.2 / 9.3）。

- 每次调用都按主键读配置库，不缓存目标本身
- 连接器按 ``(target.id, updated_at)`` 缓存；配置一变就丢弃旧客户端
- 每 target 的并发上限来自系统配置 ``target_max_concurrency``
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.connectors import base as connectors_base
from dr_panda_mcp.guards.protocol import require
from dr_panda_mcp.store.protocol import ConfigStore, Target

logger = logging.getLogger(__name__)


@dataclass
class _Pooled:
    updated_at: datetime
    connector: Any
    client: Any


class Catalog:
    """目标目录 + 客户端池 + 每 target 并发控制。"""

    def __init__(
        self,
        store: ConfigStore,
        *,
        settings_loader: Callable[[ConfigStore], Any] = settings_module.load,
        max_clients: int = 32,
    ) -> None:
        self._store = store
        self._settings_loader = settings_loader
        self._max_clients = max_clients
        self._pool: OrderedDict[int, _Pooled] = OrderedDict()
        self._semaphores: dict[int, asyncio.Semaphore] = {}
        self._limits: dict[int, int] = {}

    async def resolve(self, name: str, *, expected_type: str | None = None) -> Target:
        """按名字取目标并校验：存在、启用、类型匹配、密钥可解密。"""
        target = await self._store.get(name)
        if target is None:
            raise errors.TargetNotFound(f"目标 {name} 未登记")
        if not target.enabled:
            raise errors.TargetDisabled(f"目标 {name} 已停用")
        if expected_type is not None and target.type != expected_type:
            raise errors.TargetTypeMismatch(
                f"目标 {name} 的类型是 {target.type}，不是 {expected_type}"
            )
        if target.secret_fields and not target.secret_ok:
            raise errors.SecretUnavailable(
                f"目标 {name} 的密钥不可用，请在网页重新录入"
            )
        return target

    async def client(self, target: Target, connector: Any) -> Any:
        """取该目标的客户端；配置变更或连接器变化时重建。"""
        pooled = self._pool.get(target.id)
        if (
            pooled is not None
            and pooled.updated_at == target.updated_at
            and pooled.connector.name == connector.name
        ):
            self._pool.move_to_end(target.id)
            return pooled.client

        if pooled is not None:
            await self._close_pooled(target.id, pooled)

        client = connector.create_client(target)
        self._pool[target.id] = _Pooled(target.updated_at, connector, client)
        await self._evict_if_needed()
        return client

    async def drop(self, target_id: int) -> None:
        pooled = self._pool.pop(target_id, None)
        if pooled is not None:
            await self._close_client(pooled)

    async def close(self) -> None:
        while self._pool:
            _target_id, pooled = self._pool.popitem(last=False)
            await self._close_client(pooled)

    @asynccontextmanager
    async def slot(self, target: Target) -> AsyncIterator[None]:
        """按系统配置限制同一 target 的并发调用。"""
        limit = await self._concurrency_limit()
        semaphore = self._semaphores.get(target.id)
        if semaphore is None or self._limits.get(target.id) != limit:
            semaphore = asyncio.Semaphore(limit)
            self._semaphores[target.id] = semaphore
            self._limits[target.id] = limit
        async with semaphore:
            yield

    async def test_connection(self, name: str, connector: Any) -> None:
        """测试连接：解析目标 → 探测操作先过闸门 → 限并发 → 超时探测。"""
        target = await self.resolve(name, expected_type=connector.name)
        require(connector.probe_guard())
        client = await self.client(target, connector)
        timeout = connectors_base.timeout_seconds(target)
        async with self.slot(target):
            await connectors_base.run_with_timeout(
                connector.probe(client, target), timeout
            )

    async def _concurrency_limit(self) -> int:
        current = await self._settings_loader(self._store)
        return current.target_max_concurrency

    async def _close_pooled(self, target_id: int, pooled: _Pooled) -> None:
        self._pool.pop(target_id, None)
        await self._close_client(pooled)

    async def _close_client(self, pooled: _Pooled) -> None:
        try:
            await pooled.connector.close_client(pooled.client)
        except Exception:
            logger.warning(
                "关闭 %s 客户端失败", pooled.connector.name, exc_info=True
            )

    async def _evict_if_needed(self) -> None:
        while len(self._pool) > self._max_clients:
            _target_id, pooled = self._pool.popitem(last=False)
            await self._close_client(pooled)
