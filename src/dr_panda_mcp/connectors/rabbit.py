"""RabbitMQ 只读连接器：Management API 的队列列表与单队列详情（只发 GET）。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import rabbit as rabbit_guard
from dr_panda_mcp.guards.protocol import Decision, require
from dr_panda_mcp.store.protocol import Target


class _RabbitClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _client(self) -> httpx.AsyncClient:
        options = self.target.options
        base_url = str(options.get("management_url", "")).rstrip("/")
        if not base_url:
            raise errors.UpstreamUnavailable("rabbitmq 目标没有配置 management_url")
        return httpx.AsyncClient(
            base_url=base_url,
            auth=(options.get("user", ""), self.target.secret.get("password", "")),
            timeout=base.timeout_seconds(self.target),
        )

    async def _get(self, path: str) -> Any:
        require(rabbit_guard.check_rabbit("GET", path))
        client = self._client()
        try:
            response = await client.get(path)
            base.check_http_response(response, "rabbitmq")
            return response.json()
        except errors.DrPandaError:
            raise
        except ValueError as exc:
            raise errors.UpstreamUnavailable("rabbitmq 返回的不是 JSON") from exc
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"rabbitmq 请求失败：{exc}") from exc
        finally:
            await client.aclose()

    async def ping(self) -> None:
        await self._get("/api/overview")

    async def queues(self, vhost: str | None) -> list[dict[str, Any]]:
        path = "/api/queues" if not vhost else f"/api/queues/{quote(vhost, safe='')}"
        payload = await self._get(path)
        if not isinstance(payload, list):
            raise errors.UpstreamUnavailable("rabbitmq 队列列表格式不符合预期")
        return [base.to_jsonable(item) for item in payload if isinstance(item, dict)]

    async def queue(self, vhost: str, queue: str) -> dict[str, Any]:
        path = f"/api/queues/{quote(vhost, safe='')}/{quote(queue, safe='')}"
        payload = await self._get(path)
        if not isinstance(payload, dict):
            raise errors.UpstreamUnavailable("rabbitmq 队列详情格式不符合预期")
        return base.to_jsonable(payload)


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

    async def queues(
        self, client: _RabbitClient, target: Target, *, vhost: str | None
    ) -> list[dict[str, Any]]:
        return await client.queues(vhost)

    async def queue(
        self,
        client: _RabbitClient,
        target: Target,
        *,
        vhost: str,
        queue: str,
    ) -> dict[str, Any]:
        return await client.queue(vhost, queue)


connector = RabbitConnector()
