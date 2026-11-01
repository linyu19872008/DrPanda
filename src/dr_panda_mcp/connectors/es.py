"""Elasticsearch 最小只读连接器：集群健康探测。"""

from __future__ import annotations

import httpx

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import es as es_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _ESClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        options = self.target.options
        hosts = options.get("hosts")
        if isinstance(hosts, str):
            hosts = [part.strip() for part in hosts.split(",") if part.strip()]
        if not hosts:
            raise errors.UpstreamUnavailable("elasticsearch 目标没有配置 hosts")
        base_url = hosts[0] if "://" in hosts[0] else f"http://{hosts[0]}"

        username = options.get("username")
        auth = (
            (username, self.target.secret.get("password", ""))
            if username
            else None
        )
        headers = {}
        api_key = self.target.secret.get("api_key")
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"

        client = httpx.AsyncClient(
            base_url=base_url,
            auth=auth,
            headers=headers,
            verify=bool(options.get("verify_tls", True)),
            timeout=base.timeout_seconds(self.target),
        )
        try:
            response = await client.get("/_cluster/health")
            base.check_http_response(response, "elasticsearch")
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"elasticsearch 探测失败：{exc}") from exc
        finally:
            await client.aclose()


class ESConnector:
    name = "elasticsearch"

    def probe_guard(self) -> Decision:
        return es_guard.check_http("GET", "/_cluster/health")

    def create_client(self, target: Target) -> _ESClient:
        return _ESClient(target)

    async def probe(self, client: _ESClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _ESClient) -> None:
        return None


connector = ESConnector()
