"""MySQL 只读连接器：探测与通用只读查询。

每次连接都先设事务只读、语句超时与返回行数上限，再执行工具传入的
单条白名单语句；具体 SQL 由工具层解析、限库并强制 LIMIT。
"""

from __future__ import annotations

import ssl
from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base, classify
from dr_panda_mcp.guards import mysql as mysql_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target

SETUP_STATEMENTS = (
    "SET SESSION TRANSACTION READ ONLY",
    "SET SESSION max_execution_time = {timeout_ms}",
    "SET SESSION sql_select_limit = {max_rows}",
)


class _MySQLClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _setup(self) -> list[str]:
        timeout = base.timeout_seconds(self.target)
        return [
            "SET SESSION TRANSACTION READ ONLY",
            f"SET SESSION max_execution_time = {int(timeout * 1000)}",
            f"SET SESSION sql_select_limit = {base.max_rows(self.target)}",
        ]

    async def ping(self) -> None:
        try:
            import asyncmy
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(errors.missing_client_message("mysql")) from exc

        connection = await _connect(asyncmy, self.target)
        try:
            async with connection.cursor() as cursor:
                for statement in [*self._setup(), "SELECT 1"]:
                    await cursor.execute(statement)
                await cursor.fetchone()
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise classify.mysql_error(exc, "mysql 探测失败") from exc
        finally:
            await _close(connection)

    async def fetch_rows(self, sql: str) -> list[dict[str, Any]]:
        try:
            import asyncmy
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(errors.missing_client_message("mysql")) from exc

        async def _fetch() -> list[dict[str, Any]]:
            connection = await _connect(asyncmy, self.target)
            try:
                async with connection.cursor() as cursor:
                    for statement in self._setup():
                        await cursor.execute(statement)
                    await cursor.execute(sql)
                    columns = [item[0] for item in (cursor.description or [])]
                    records = await cursor.fetchall()
                    return [
                        {
                            str(column): base.to_jsonable(value)
                            for column, value in zip(columns, record)
                        }
                        for record in records
                    ]
            finally:
                await _close(connection)

        try:
            return await base.run_with_timeout(
                _fetch(), base.timeout_seconds(self.target)
            )
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise classify.mysql_error(exc, "mysql 查询失败") from exc


async def _connect(asyncmy: Any, target: Target) -> Any:
    options = target.options
    kwargs: dict[str, Any] = {
        "host": options.get("host", "127.0.0.1"),
        "port": int(options.get("port", 3306)),
        "user": options.get("user", ""),
        "password": target.secret.get("password", ""),
        "db": options.get("default_db") or None,
        "connect_timeout": base.timeout_seconds(target),
        "autocommit": True,
    }
    if options.get("ssl"):
        kwargs["ssl"] = _ssl_context(target)
    return await asyncmy.connect(**kwargs)


def _ssl_context(target: Target) -> ssl.SSLContext:
    return base.build_tls_context(
        ca_pem=str(target.options.get("ca_pem") or "").strip(),
        client_cert=target.secret.get("client_cert", ""),
        client_key=target.secret.get("client_key", ""),
    )


async def _close(connection: Any) -> None:
    closer = getattr(connection, "ensure_closed", None)
    if closer is not None:
        await closer()
    else:  # pragma: no cover - asyncmy 走 ensure_closed
        connection.close()


class MySQLConnector:
    name = "mysql"

    def probe_guard(self) -> Decision:
        return mysql_guard.check_sql("SELECT 1")

    def create_client(self, target: Target) -> _MySQLClient:
        return _MySQLClient(target)

    async def probe(self, client: _MySQLClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _MySQLClient) -> None:
        return None

    async def fetch_rows(
        self, client: _MySQLClient, target: Target, sql: str
    ) -> list[dict[str, Any]]:
        return await client.fetch_rows(sql)


connector = MySQLConnector()
