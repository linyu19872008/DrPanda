"""Redis 最小只读连接器：``PING`` 探测。"""

from __future__ import annotations

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import redis as redis_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _RedisClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        try:
            import redis.asyncio as redis_async
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "redis 客户端未安装：uv sync --extra redis"
            ) from exc

        options = self.target.options
        client = redis_async.Redis(
            host=options.get("host", "127.0.0.1"),
            port=int(options.get("port", 6379)),
            password=self.target.secret.get("password") or None,
            db=int(options.get("db", 0)),
            ssl=bool(options.get("tls", False)),
            socket_connect_timeout=base.timeout_seconds(self.target),
            socket_timeout=base.timeout_seconds(self.target),
        )
        try:
            await client.ping()
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"redis 探测失败：{exc}") from exc
        finally:
            await client.aclose()


class RedisConnector:
    name = "redis"

    def probe_guard(self) -> Decision:
        return redis_guard.check_redis("PING")

    def create_client(self, target: Target) -> _RedisClient:
        return _RedisClient(target)

    async def probe(self, client: _RedisClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _RedisClient) -> None:
        return None


connector = RedisConnector()
