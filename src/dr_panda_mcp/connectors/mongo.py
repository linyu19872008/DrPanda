"""Mongo 只读连接器：集合概览、find、aggregate、stats。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import mongo as mongo_guard
from dr_panda_mcp.guards.protocol import Decision, require
from dr_panda_mcp.store.protocol import Target


class _MongoClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _client(self):
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "mongo 客户端未安装：uv sync --extra mongo"
            ) from exc
        uri = self.target.secret.get("uri") or _build_uri(self.target)
        return AsyncIOMotorClient(
            uri, serverSelectionTimeoutMS=int(base.timeout_seconds(self.target) * 1000)
        )

    async def ping(self) -> None:
        client = self._client()
        try:
            await client.admin.command("ping")
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mongo 探测失败：{exc}") from exc
        finally:
            client.close()

    async def collections(self, db_name: str, limit: int) -> list[dict[str, Any]]:
        require(mongo_guard.check_mongo_command("listCollections", {}))
        client = self._client()
        try:
            db = client[db_name]
            names = sorted(await db.list_collection_names())[:limit]
            rows: list[dict[str, Any]] = []
            for name in names:
                require(mongo_guard.check_mongo_command("collStats", {}))
                stats = await db.command("collStats", name)
                indexes = await db[name].index_information()
                rows.append(
                    {
                        "collection": name,
                        "type": "view" if stats.get("viewName") else "collection",
                        "documents": stats.get("count"),
                        "indexes": len(indexes),
                    }
                )
            return rows
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mongo 集合列表失败：{exc}") from exc
        finally:
            client.close()

    async def find(
        self,
        db_name: str,
        collection: str,
        filter_: dict[str, Any],
        projection: dict[str, Any] | None,
        sort: dict[str, Any] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        require(mongo_guard.check_mongo_command("find", {"filter": filter_}))
        client = self._client()
        try:
            cursor = client[db_name][collection].find(
                filter_, projection, max_time_ms=int(base.timeout_seconds(self.target) * 1000)
            )
            if sort:
                cursor = cursor.sort(list(sort.items()))
            documents = await cursor.limit(limit).to_list(length=limit)
            return [base.to_jsonable(document) for document in documents]
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mongo find 失败：{exc}") from exc
        finally:
            client.close()

    async def aggregate(
        self,
        db_name: str,
        collection: str,
        pipeline: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        require(mongo_guard.check_mongo_command("aggregate", {"pipeline": pipeline}))
        client = self._client()
        try:
            staged = [*pipeline, {"$limit": limit}]
            cursor = client[db_name][collection].aggregate(
                staged, maxTimeMS=int(base.timeout_seconds(self.target) * 1000)
            )
            documents = await cursor.to_list(length=limit)
            return [base.to_jsonable(document) for document in documents]
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mongo aggregate 失败：{exc}") from exc
        finally:
            client.close()

    async def stats(
        self, db_name: str, collection: str | None
    ) -> list[dict[str, Any]]:
        command = "collStats" if collection else "dbStats"
        require(mongo_guard.check_mongo_command(command, {}))
        client = self._client()
        try:
            db = client[db_name]
            payload = (
                await db.command("collStats", collection)
                if collection
                else await db.command("dbStats")
            )
            return [base.to_jsonable(payload)]
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mongo stats 失败：{exc}") from exc
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
        return (
            f"mongodb://{quote(str(user), safe='')}:{quote(str(password or ''), safe='')}"
            f"@{host}:{port}/?authSource={quote(str(auth_source), safe='')}"
        )
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

    async def collections(
        self, client: _MongoClient, target: Target, *, db: str, limit: int
    ) -> list[dict[str, Any]]:
        return await client.collections(db, limit)

    async def find(
        self,
        client: _MongoClient,
        target: Target,
        *,
        db: str,
        collection: str,
        filter_: dict[str, Any],
        projection: dict[str, Any] | None,
        sort: dict[str, Any] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await client.find(db, collection, filter_, projection, sort, limit)

    async def aggregate(
        self,
        client: _MongoClient,
        target: Target,
        *,
        db: str,
        collection: str,
        pipeline: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        return await client.aggregate(db, collection, pipeline, limit)

    async def stats(
        self,
        client: _MongoClient,
        target: Target,
        *,
        db: str,
        collection: str | None,
    ) -> list[dict[str, Any]]:
        return await client.stats(db, collection)


connector = MongoConnector()
