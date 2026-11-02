"""Elasticsearch 只读连接器：mapping、search、health、index stats。"""

from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import quote

import httpx

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import es as es_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


def _tls_verify(target: Target) -> bool | ssl.SSLContext:
    options = target.options
    ca_pem = str(options.get("ca_pem") or "").strip()
    client_cert = target.secret.get("client_cert", "")
    client_key = target.secret.get("client_key", "")
    if ca_pem or client_cert or client_key:
        return base.build_tls_context(
            ca_pem=ca_pem,
            client_cert=client_cert,
            client_key=client_key,
        )
    return bool(options.get("verify_tls", True))


class _ESClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _base_urls(self) -> list[str]:
        options = self.target.options
        hosts = options.get("hosts")
        if isinstance(hosts, str):
            hosts = [part.strip() for part in hosts.split(",") if part.strip()]
        if not hosts:
            raise errors.UpstreamUnavailable("elasticsearch 目标没有配置 hosts")
        return [host if "://" in host else f"http://{host}" for host in hosts]

    def _client(self, base_url: str) -> httpx.AsyncClient:
        options = self.target.options
        username = options.get("username")
        auth = (
            (username, self.target.secret.get("password", "")) if username else None
        )
        headers: dict[str, str] = {}
        api_key = self.target.secret.get("api_key")
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        return httpx.AsyncClient(
            base_url=base_url,
            auth=auth,
            headers=headers,
            verify=_tls_verify(self.target),
            timeout=base.timeout_seconds(self.target),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for base_url in self._base_urls():
            client = self._client(base_url)
            try:
                response, _ = await base.stream_http(
                    client,
                    method,
                    path,
                    component="elasticsearch",
                    limit=base.max_bytes(self.target),
                    json_body=body,
                )
                if response.status_code >= 500:
                    last_error = errors.UpstreamUnavailable(
                        f"elasticsearch 返回 HTTP {response.status_code}"
                    )
                    continue
                return response
            except errors.UpstreamNotFound:
                raise
            except Exception as exc:  # noqa: BLE001 - 统一映射并尝试下一个 host
                last_error = exc
            finally:
                await client.aclose()
        raise errors.UpstreamUnavailable(
            f"elasticsearch 所有 host 均不可用：{last_error}"
        )

    async def ping(self) -> None:
        await self._request("GET", "/_cluster/health")

    async def mapping(self, index: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        path = f"/{quote(index, safe='')}/_mapping"
        mapping_payload = (await self._request("GET", path)).json()
        settings_payload = (
            await self._request("GET", f"/{quote(index, safe='')}/_settings")
        ).json()
        entry = mapping_payload.get(index, {}) if isinstance(mapping_payload, dict) else {}
        properties = (entry.get("mappings") or {}).get("properties") or {}
        rows: list[dict[str, Any]] = []

        def walk(node: dict[str, Any], prefix: str = "") -> None:
            for name, spec in node.items():
                if not isinstance(spec, dict):
                    continue
                field = f"{prefix}.{name}" if prefix else name
                if "properties" in spec:
                    walk(spec["properties"], field)
                else:
                    rows.append(
                        {
                            "field": field,
                            "type": spec.get("type"),
                            "analyzer": spec.get("analyzer")
                            or spec.get("search_analyzer"),
                        }
                    )

        walk(properties)
        settings_entry = settings_payload.get(index, {}) if isinstance(settings_payload, dict) else {}
        settings = (settings_entry.get("settings") or {}).get("index") or {}
        stats = {
            "shards": settings.get("number_of_shards"),
            "replicas": settings.get("number_of_replicas"),
        }
        return rows, stats

    async def search(
        self, index: str, body: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        payload = (
            await self._request("POST", f"/{quote(index, safe='')}/_search", body=body)
        ).json()
        hits = payload.get("hits") or {}
        rows: list[dict[str, Any]] = []
        for hit in hits.get("hits") or []:
            row = {
                "_index": hit.get("_index"),
                "_id": hit.get("_id"),
                "_score": hit.get("_score"),
            }
            if "sort" in hit:
                row["_sort"] = hit.get("sort")
            source = hit.get("_source")
            if isinstance(source, dict):
                row.update(source)
            rows.append(base.to_jsonable(row))
        total = hits.get("total")
        if isinstance(total, dict):
            total = total.get("value")
        return rows, {"total": total, "took": payload.get("took")}

    async def health(self) -> dict[str, Any]:
        payload = (await self._request("GET", "/_cluster/health")).json()
        keys = [
            "cluster_name",
            "status",
            "number_of_nodes",
            "number_of_data_nodes",
            "active_primary_shards",
            "active_shards",
            "relocating_shards",
            "initializing_shards",
            "unassigned_shards",
            "delayed_unassigned_shards",
        ]
        return {key: payload.get(key) for key in keys if key in payload}

    async def index_stats(self, index: str) -> list[dict[str, Any]]:
        payload = (
            await self._request("GET", f"/{quote(index, safe='')}/_stats")
        ).json()
        rows: list[dict[str, Any]] = []
        for name, entry in (payload.get("indices") or {}).items():
            primaries = (entry.get("primaries") or {})
            total = (entry.get("total") or {})
            rows.append(
                {
                    "index": name,
                    "primaries_docs": (primaries.get("docs") or {}).get("count"),
                    "primaries_size_bytes": (primaries.get("store") or {}).get(
                        "size_in_bytes"
                    ),
                    "total_docs": (total.get("docs") or {}).get("count"),
                    "total_size_bytes": (total.get("store") or {}).get(
                        "size_in_bytes"
                    ),
                }
            )
        return rows


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

    async def mapping(
        self, client: _ESClient, target: Target, *, index: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return await client.mapping(index)

    async def search(
        self, client: _ESClient, target: Target, *, index: str, body: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return await client.search(index, body)

    async def health(
        self, client: _ESClient, target: Target
    ) -> dict[str, Any]:
        return await client.health()

    async def index_stats(
        self, client: _ESClient, target: Target, *, index: str
    ) -> list[dict[str, Any]]:
        return await client.index_stats(index)


connector = ESConnector()
