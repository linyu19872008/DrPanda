"""RabbitMQ 最小只读连接器：读取 Management API 概览（只发 GET）。"""

from __future__ import annotations

import httpx

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import rabbit as rabbit_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _RabbitClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        options = self.target.options
        base_url = options.get("management_url", "").rstrip("/")
        if not base_url:
            raise errors.UpstreamUnavailable("rabbitmq 目标没有配置 management_url")
        client = httpx.AsyncClient(
            base_url=base_url,
            auth=(
                options.get("user", ""),
                self.target.secret.get("password", ""),
            ),
            timeout=base.timeout_seconds(self.target),
        )
        try:
            response = await client.get("/api/overview")
            base.check_http_response(response, "rabbitmq")
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"rabbitmq 探测失败：{exc}") from exc
        finally:
            await client.aclose()


class RabbitConnector:
    name = "rabbitmq"

    def probe_guard(self) -> Decision:
        return rabbit_guard.check_rabbit("GET", "/api/overview")

    def create_client(self, target: Target) -> _RabbitClient:
        return _RabbitClient(target)

    async def probe(self, client: _RabbitClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _RabbitClient) -> None:
        return None


connector = RabbitConnector()
