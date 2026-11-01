"""Mongo 最小只读连接器：``ping`` 探测。"""

from __future__ import annotations

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import mongo as mongo_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _MongoClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "mongo 客户端未安装：uv sync --extra mongo"
            ) from exc

        timeout = base.timeout_seconds(self.target)
        uri = self.target.secret.get("uri") or _build_uri(self.target)
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=int(timeout * 1000))
        try:
            await client.admin.command("ping")
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mongo 探测失败：{exc}") from exc
        finally:
            client.close()


def _build_uri(target: Target) -> str:
    options = target.options
    host = options.get("host", "127.0.0.1")
    port = int(options.get("port", 27017))
    user = options.get("user")
    password = target.secret.get("password")
    auth_source = options.get("auth_source", "admin")
    if user:
        return f"mongodb://{user}:{password}@{host}:{port}/?authSource={auth_source}"
    return f"mongodb://{host}:{port}/"


class MongoConnector:
    name = "mongo"

    def probe_guard(self) -> Decision:
        return mongo_guard.check_mongo_command("ping", {})

    def create_client(self, target: Target) -> _MongoClient:
        return _MongoClient(target)

    async def probe(self, client: _MongoClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _MongoClient) -> None:
        return None


connector = MongoConnector()
