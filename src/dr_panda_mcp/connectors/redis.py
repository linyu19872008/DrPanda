"""Redis 只读连接器：单 key 查看、SCAN、INFO、SLOWLOG。"""

from __future__ import annotations

import os
import tempfile
from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import redis as redis_guard
from dr_panda_mcp.guards.protocol import Decision, require
from dr_panda_mcp.store.protocol import Target


class _RedisClient:
    def __init__(self, target: Target) -> None:
        self.target = target
        self._cert_path: str | None = None
        self._key_path: str | None = None
        if target.options.get("tls"):
            cert = target.secret.get("client_cert", "")
            key = target.secret.get("client_key", "")
            if cert or key:
                if not (cert and key):
                    raise errors.UpstreamUnavailable(
                        "redis 客户端证书与私钥必须同时提供"
                    )
                self._cert_path = _temp_pem(cert, "cert")
                self._key_path = _temp_pem(key, "key")
                os.chmod(self._key_path, 0o600)

    def close_files(self) -> None:
        for path in (self._cert_path, self._key_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _client(self):
        try:
            import redis.asyncio as redis_async
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(errors.missing_client_message("redis")) from exc
        options = self.target.options
        kwargs: dict[str, Any] = {
            "host": options.get("host", "127.0.0.1"),
            "port": int(options.get("port", 6379)),
            "password": self.target.secret.get("password") or None,
            "db": int(options.get("db", 0)),
            "socket_connect_timeout": base.timeout_seconds(self.target),
            "socket_timeout": base.timeout_seconds(self.target),
            "decode_responses": True,
        }
        username = str(options.get("username") or "").strip()
        if username:
            kwargs["username"] = username
        if options.get("tls"):
            ca_pem = str(options.get("ca_pem") or "").strip()
            if ca_pem:
                kwargs["ssl_ca_data"] = ca_pem
            kwargs["ssl"] = True
            if self._cert_path and self._key_path:
                kwargs["ssl_certfile"] = self._cert_path
                kwargs["ssl_keyfile"] = self._key_path
        return redis_async.Redis(**kwargs)

    async def _run(self, operation):
        client = self._client()
        try:
            return await base.run_with_timeout(
                operation(client), base.timeout_seconds(self.target)
            )
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"redis 读取失败：{exc}") from exc
        finally:
            await client.aclose()

    async def ping(self) -> None:
        await self._run(lambda client: client.ping())

    async def inspect(self, key: str, limit: int, byte_limit: int) -> dict[str, Any]:
        async def operation(client):
            require(redis_guard.check_redis("TYPE", [key]))
            kind = await client.type(key)
            require(redis_guard.check_redis("TTL", [key]))
            ttl = await client.ttl(key)
            value: Any = None
            if kind == "string":
                require(redis_guard.check_redis("STRLEN", [key]))
                size = await client.strlen(key)
                if size > byte_limit:
                    raise errors.GuardRejected(
                        f"redis string {key} 有 {size} 字节，超过目标字节上限 {byte_limit}",
                        code=errors.DANGEROUS_OPERATION,
                    )
                require(redis_guard.check_redis("GET", [key]))
                value = await client.get(key)
            elif kind == "list":
                require(redis_guard.check_redis("LLEN", [key]))
                size = await client.llen(key)
                _ensure_within(size, limit, "list", key)
                require(redis_guard.check_redis("LRANGE", [key, 0, limit - 1]))
                value = await client.lrange(key, 0, limit - 1)
            elif kind == "set":
                require(redis_guard.check_redis("SCARD", [key]))
                size = await client.scard(key)
                _ensure_within(size, limit, "set", key)
                require(redis_guard.check_redis("SMEMBERS", [key]))
                value = await client.smembers(key)
            elif kind == "zset":
                require(redis_guard.check_redis("ZCARD", [key]))
                size = await client.zcard(key)
                _ensure_within(size, limit, "zset", key)
                require(redis_guard.check_redis("ZRANGE", [key, 0, limit - 1]))
                value = await client.zrange(key, 0, limit - 1, withscores=True)
            elif kind == "hash":
                count = min(limit, 200)
                require(redis_guard.check_redis("HSCAN", [key, 0, "COUNT", count]))
                value = await client.hscan(key, 0, count=count)
            return {"key": key, "type": kind, "ttl": ttl, "value": base.to_jsonable(value)}

        return await self._run(operation)

    async def scan(
        self, pattern: str, count: int, cursor: int
    ) -> tuple[list[str], int]:
        async def operation(client):
            require(
                redis_guard.check_redis(
                    "SCAN", [cursor, "MATCH", pattern, "COUNT", count]
                )
            )
            next_cursor, keys = await client.scan(
                cursor=cursor, match=pattern, count=count
            )
            return sorted(keys), int(next_cursor)

        return await self._run(operation)

    async def info(self, section: str | None) -> dict[str, Any]:
        async def operation(client):
            require(redis_guard.check_redis("INFO", [section] if section else []))
            payload = await client.info(section or None)
            if isinstance(payload, dict):
                return base.to_jsonable(payload)
            parsed: dict[str, Any] = {}
            for line in str(payload).splitlines():
                if line and not line.startswith("#") and ":" in line:
                    name, value = line.split(":", 1)
                    parsed[name] = value
            return parsed

        return await self._run(operation)

    async def slowlog(self, count: int) -> list[dict[str, Any]]:
        async def operation(client):
            require(redis_guard.check_redis("SLOWLOG", ["GET", count]))
            entries = await client.slowlog_get(count)
            return [base.to_jsonable(entry) for entry in entries]

        return await self._run(operation)


def _temp_pem(content: str, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=f".{suffix}.pem", delete=False
    ) as handle:
        handle.write(content)
        path = handle.name
    os.chmod(path, 0o600)
    return path


def _ensure_within(size: int, limit: int, kind: str, key: str) -> None:
    if size > limit:
        raise errors.GuardRejected(
            f"redis {kind} {key} 有 {size} 个元素，超过目标上限 {limit}",
            code=errors.DANGEROUS_OPERATION,
        )


class RedisConnector:
    name = "redis"

    def probe_guard(self) -> Decision:
        return redis_guard.check_redis("PING")

    def create_client(self, target: Target) -> _RedisClient:
        return _RedisClient(target)

    async def probe(self, client: _RedisClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _RedisClient) -> None:
        client.close_files()

    async def inspect(
        self,
        client: _RedisClient,
        target: Target,
        *,
        key: str,
        limit: int,
        byte_limit: int,
    ) -> dict[str, Any]:
        return await client.inspect(key, limit, byte_limit)

    async def scan(
        self,
        client: _RedisClient,
        target: Target,
        *,
        pattern: str,
        count: int,
        cursor: int,
    ) -> tuple[list[str], int]:
        return await client.scan(pattern, count, cursor)

    async def info(
        self, client: _RedisClient, target: Target, *, section: str | None
    ) -> dict[str, Any]:
        return await client.info(section)

    async def slowlog(
        self, client: _RedisClient, target: Target, *, count: int
    ) -> list[dict[str, Any]]:
        return await client.slowlog(count)


connector = RedisConnector()
