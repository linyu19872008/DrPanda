"""MySQL 最小只读连接器（测试连接用）。

连接建立后先把会话设为事务只读、设置语句超时与返回行数上限，
再执行 ``SELECT 1``。真正的排查工具在后续里程碑接入。
"""

from __future__ import annotations

from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import mysql as mysql_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _MySQLClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        timeout = base.timeout_seconds(self.target)
        try:
            import asyncmy
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "mysql 客户端未安装：uv sync --extra mysql"
            ) from exc

        connection = await _connect(asyncmy, self.target, timeout)
        statements = [
            "SET SESSION TRANSACTION READ ONLY",
            f"SET SESSION max_execution_time = {int(timeout * 1000)}",
            f"SET SESSION sql_select_limit = {base.max_rows(self.target)}",
            "SELECT 1",
        ]
        try:
            async with connection.cursor() as cursor:
                for statement in statements:
                    await cursor.execute(statement)
                await cursor.fetchone()
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"mysql 探测失败：{exc}") from exc
        finally:
            closer = getattr(connection, "ensure_closed", None)
            if closer is not None:
                await closer()
            else:  # pragma: no cover - asyncmy 走 ensure_closed
                connection.close()


async def _connect(asyncmy: Any, target: Target, timeout: float) -> Any:
    options = target.options
    return await asyncmy.connect(
        host=options.get("host", "127.0.0.1"),
        port=int(options.get("port", 3306)),
        user=options.get("user", ""),
        password=target.secret.get("password", ""),
        db=options.get("default_db") or None,
        connect_timeout=timeout,
        autocommit=True,
    )


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


connector = MySQLConnector()
