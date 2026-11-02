"""Mongo 只读连接器：认证模式、TLS、集合概览、find、aggregate、stats。"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote, urlsplit

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import mongo as mongo_guard
from dr_panda_mcp.guards.protocol import Decision, require
from dr_panda_mcp.store.protocol import Target

AUTH_MODES = frozenset({"none", "password", "uri"})


def _auth_mode(target: Target) -> str:
    mode = target.options.get("auth_mode")
    if mode in AUTH_MODES:
        return str(mode)
    # 兼容未写 auth_mode 的旧 target
    if target.secret.get("uri") or "uri" in target.secret_fields:
        return "uri"
    if target.options.get("user") or "password" in target.secret_fields:
        return "password"
    return "none"


def _build_uri(target: Target) -> str:
    options = target.options
    mode = _auth_mode(target)
    if mode == "uri":
        uri = str(target.secret.get("uri") or "").strip()
        if not uri:
            raise errors.UpstreamUnavailable("mongo 目标未配置连接 URI")
        scheme = urlsplit(uri).scheme
        if scheme not in {"mongodb", "mongodb+srv"}:
            raise errors.UpstreamUnavailable("mongo 连接 URI 必须以 mongodb:// 或 mongodb+srv:// 开头")
        return uri

    host = str(options.get("host") or "").strip()
    if not host:
        raise errors.UpstreamUnavailable("mongo 目标未配置主机")
    port = int(options.get("port", 27017))
    if mode == "password":
        user = str(options.get("user") or "").strip()
        password = target.secret.get("password", "")
        if not user or not password:
            raise errors.UpstreamUnavailable("mongo 密码模式缺少用户或密码")
        auth_source = quote(str(options.get("auth_source") or "admin"), safe="")
        return (
            f"mongodb://{quote(user, safe='')}:{quote(str(password), safe='')}"
            f"@{host}:{port}/?authSource={auth_source}"
        )
    return f"mongodb://{host}:{port}/"


class _MongoClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _tls_kwargs(self) -> tuple[dict[str, Any], list[str]]:
        options = self.target.options
        ca_pem = str(options.get("ca_pem") or "").strip()
        client_cert = self.target.secret.get("client_cert", "")
        client_key = self.target.secret.get("client_key", "")
        tls = bool(options.get("tls"))
        if not tls and not (ca_pem or client_cert or client_key):
            return {}, []

        if not tls:
            raise errors.UpstreamUnavailable("mongo 配置 TLS 材料时必须启用 TLS")
        if not (client_cert and client_key) and (client_cert or client_key):
            raise errors.UpstreamUnavailable("mongo 客户端证书与私钥必须同时提供")

        kwargs: dict[str, Any] = {"tls": True}
        paths: list[str] = []
        try:
            if ca_pem:
                kwargs["tlsCAFile"] = _temp_text(ca_pem, "ca", 0o600)
                paths.append(kwargs["tlsCAFile"])
            if client_cert and client_key:
                # PyMongo 的 tlsCertificateKeyFile 需要证书与私钥在同一个文件。
                combined = client_cert.rstrip() + "\n" + client_key
                kwargs["tlsCertificateKeyFile"] = _temp_text(combined, "client", 0o600)
                paths.append(kwargs["tlsCertificateKeyFile"])
        except Exception:
            for path in paths:
                _unlink(path)
            raise
        return kwargs, paths

    @asynccontextmanager
    async def _connected(self) -> AsyncIterator[Any]:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "mongo 客户端未安装：uv sync --extra mongo"
            ) from exc

        tls_kwargs, paths = self._tls_kwargs()
        client = None
        try:
            timeout = base.timeout_seconds(self.target)
            # 留出 20% 给工具级 deadline，让驱动先报 ServerSelection/TLS 错误，
            # 避免整调用超时把认证/证书错误掩盖成 UPSTREAM_TIMEOUT。
            client = AsyncIOMotorClient(
                _build_uri(self.target),
                serverSelectionTimeoutMS=max(int(timeout * 0.8 * 1000), 1000),
                **tls_kwargs,
            )
            yield client
        finally:
            if client is not None:
                client.close()
            for path in paths:
                _unlink(path)

    async def ping(self) -> None:
        async with self._connected() as client:
            try:
                await client.admin.command("ping")
            except Exception as exc:
                raise errors.UpstreamUnavailable(f"mongo 探测失败：{exc}") from exc

    async def collections(self, db_name: str, limit: int) -> list[dict[str, Any]]:
        require(mongo_guard.check_mongo_command("listCollections", {}))
        async with self._connected() as client:
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
        async with self._connected() as client:
            try:
                cursor = client[db_name][collection].find(
                    filter_,
                    projection,
                    max_time_ms=int(base.timeout_seconds(self.target) * 1000),
                )
                if sort:
                    cursor = cursor.sort(list(sort.items()))
                documents = await cursor.limit(limit).to_list(length=limit)
                return [base.to_jsonable(document) for document in documents]
            except errors.DrPandaError:
                raise
            except Exception as exc:
                raise errors.UpstreamUnavailable(f"mongo find 失败：{exc}") from exc

    async def aggregate(
        self,
        db_name: str,
        collection: str,
        pipeline: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        require(mongo_guard.check_mongo_command("aggregate", {"pipeline": pipeline}))
        async with self._connected() as client:
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

    async def stats(
        self, db_name: str, collection: str | None
    ) -> list[dict[str, Any]]:
        command = "collStats" if collection else "dbStats"
        require(mongo_guard.check_mongo_command(command, {}))
        async with self._connected() as client:
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


def _temp_text(content: str, suffix: str, mode: int) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=f".{suffix}.pem", delete=False
    ) as handle:
        handle.write(content)
        path = handle.name
    os.chmod(path, mode)
    return path


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


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
