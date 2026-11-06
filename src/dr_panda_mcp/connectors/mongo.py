"""Mongo 只读连接器：认证模式、TLS、集合概览、find、aggregate、stats。"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote, urlsplit

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base, classify
from dr_panda_mcp.guards import mongo as mongo_guard
from dr_panda_mcp.guards.protocol import Decision, require
from dr_panda_mcp.store.protocol import Target

AUTH_MODES = frozenset({"none", "password", "uri"})

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _is_hex_escape(text: str, index: int) -> bool:
    """``text[index]`` 是 ``%`` 时，判断后两位是否构成合法的百分号转义。"""
    return (
        index + 2 < len(text)
        and text[index + 1] in _HEX_DIGITS
        and text[index + 2] in _HEX_DIGITS
    )


def _has_unquoted_percent(text: str) -> bool:
    return any(
        char == "%" and not _is_hex_escape(text, index)
        for index, char in enumerate(text)
    )


def _escape_credential(text: str) -> str:
    """把会破坏 URI 结构的字符编码掉，保留用户已写好的 ``%XX``。"""
    pieces: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "%" and _is_hex_escape(text, index):
            pieces.append(text[index : index + 3])
            index += 3
            continue
        if char == "%":
            pieces.append("%25")
        elif char == "@":
            pieces.append("%40")
        elif char == ":":
            pieces.append("%3A")
        else:
            pieces.append(char)
        index += 1
    return "".join(pieces)


def _userinfo_is_valid(userinfo: str) -> bool:
    """与 pymongo 的 userinfo 校验保持一致，避免对合法 URI 二次编码。"""
    if "@" in userinfo or userinfo.count(":") > 1 or _has_unquoted_percent(userinfo):
        return False
    return bool(userinfo.partition(":")[0])


def _normalize_uri_credentials(uri: str) -> str:
    """URI 模式兜底：凭证未转义时自动编码，已合法的 URI 原样返回。

    pymongo 在构造客户端时解析 URI：``//`` 之后、最后一个 ``@`` 之前的 userinfo
    里只要还有 ``@``、多个 ``:`` 或非法 ``%``，就直接抛 ``InvalidURI``。裸密码
    常见于 ``p@ss`` / ``pa:ss`` / ``100%zz``，这里按已知边界重新编码——
    最后一个 ``@`` 前是 userinfo，userinfo 里第一个 ``:`` 前是用户名。
    已经写好的 ``%XX`` 保持不变，避免把 ``%40`` 二次编码成 ``%2540``。
    """
    scheme, separator, rest = uri.partition("://")
    if not separator:
        return uri
    cut = len(rest)
    for marker in "/?#":
        position = rest.find(marker)
        if position != -1:
            cut = min(cut, position)
    authority, tail = rest[:cut], rest[cut:]
    if "@" not in authority:
        return uri
    userinfo, host_part = authority.rsplit("@", 1)
    if _userinfo_is_valid(userinfo):
        return uri
    user, password_separator, password = userinfo.partition(":")
    if not user:
        raise errors.UpstreamUnavailable(
            "mongo connection URI has an empty user name; the format is "
            "mongodb://user:password@host:port/"
        )
    encoded_user = _escape_credential(user)
    if not password_separator:
        return f"{scheme}://{encoded_user}@{host_part}{tail}"
    return f"{scheme}://{encoded_user}:{_escape_credential(password)}@{host_part}{tail}"


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
            raise errors.UpstreamUnavailable("mongo target has no connection URI configured")
        scheme = urlsplit(uri).scheme
        if scheme not in {"mongodb", "mongodb+srv"}:
            raise errors.UpstreamUnavailable("mongo connection URI must start with mongodb:// or mongodb+srv://")
        return _normalize_uri_credentials(uri)

    host = str(options.get("host") or "").strip()
    if not host:
        raise errors.UpstreamUnavailable("mongo target has no host configured")
    port = int(options.get("port", 27017))
    if mode == "password":
        user = str(options.get("user") or "").strip()
        password = target.secret.get("password", "")
        if not user or not password:
            raise errors.UpstreamUnavailable("mongo password mode is missing a user or password")
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
            raise errors.UpstreamUnavailable("TLS must be enabled when TLS material is configured for mongo")
        if not (client_cert and client_key) and (client_cert or client_key):
            raise errors.UpstreamUnavailable("mongo client certificate and private key must be provided together")

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
            raise errors.UpstreamUnavailable(errors.missing_client_message("mongo")) from exc

        tls_kwargs, paths = self._tls_kwargs()
        client = None
        try:
            timeout = base.timeout_seconds(self.target)
            # 留出 20% 给工具级 deadline，让驱动先报 ServerSelection/TLS 错误，
            # 避免整调用超时把认证/证书错误掩盖成 UPSTREAM_TIMEOUT。
            try:
                client = AsyncIOMotorClient(
                    _build_uri(self.target),
                    serverSelectionTimeoutMS=max(int(timeout * 0.8 * 1000), 1000),
                    **tls_kwargs,
                )
            except errors.DrPandaError:
                raise
            except Exception as exc:
                # 驱动在构造阶段就解析 URI；把 InvalidURI 之类的异常转成可读错误，
                # 否则会以“未预期错误”直出网页。
                raise errors.UpstreamUnavailable(f"mongo connection string cannot be parsed: {exc}") from exc
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
                raise classify.mongo_error(exc, "mongo probe failed") from exc

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
                raise classify.mongo_error(exc, "mongo collection listing failed") from exc

    async def find(
        self,
        db_name: str,
        collection: str,
        filter_: dict[str, Any],
        projection: dict[str, Any] | None,
        sort: dict[str, Any] | None,
        limit: int,
        skip: int = 0,
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
                if skip:
                    cursor = cursor.skip(skip)
                documents = await cursor.limit(limit).to_list(length=limit)
                return [base.to_jsonable(document) for document in documents]
            except errors.DrPandaError:
                raise
            except Exception as exc:
                raise classify.mongo_error(exc, "mongo find failed") from exc

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
                raise classify.mongo_error(exc, "mongo aggregate failed") from exc

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
                raise classify.mongo_error(exc, "mongo stats failed") from exc


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
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        return await client.find(db, collection, filter_, projection, sort, limit, skip)

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
