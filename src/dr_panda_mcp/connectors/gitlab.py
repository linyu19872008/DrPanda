"""GitLab 只读连接器：当前用户、代码搜索、读文件、blame（只发 GET）。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import gitlab as gitlab_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _GitLabClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _client(self) -> httpx.AsyncClient:
        options = self.target.options
        base_url = str(options.get("base_url", "")).rstrip("/")
        if not base_url:
            raise errors.UpstreamUnavailable("gitlab target has no base_url configured")
        return httpx.AsyncClient(
            base_url=base_url,
            headers={"PRIVATE-TOKEN": self.target.secret.get("token", "")},
            timeout=base.timeout_seconds(self.target),
        )

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        truncate: bool = False,
    ) -> tuple[httpx.Response, bool]:
        client = self._client()
        try:
            response, cut = await base.stream_http(
                client,
                "GET",
                path,
                component="gitlab",
                limit=base.max_bytes(self.target),
                params=params,
                truncate=truncate,
            )
            return response, cut
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"gitlab request failed: {exc}") from exc
        finally:
            await client.aclose()

    async def ping(self) -> None:
        await self._get("/api/v4/user")

    async def search_code(
        self,
        project: str,
        query: str,
        *,
        ref: str | None,
        per_page: int,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "scope": "blobs",
            "search": query,
            "per_page": per_page,
        }
        if ref:
            params["ref"] = ref
        if page > 1:
            params["page"] = page
        response, _ = await self._get(
            f"/api/v4/projects/{quote(project, safe='')}/search", params=params
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise errors.UpstreamUnavailable("gitlab returned non-JSON content") from exc
        if not isinstance(payload, list):
            raise errors.UpstreamUnavailable("gitlab search results have an unexpected format")
        return [item for item in payload if isinstance(item, dict)]

    async def get_file(
        self, project: str, path: str, *, ref: str | None
    ) -> tuple[str, bool]:
        params = {"ref": ref} if ref else None
        response, cut = await self._get(
            f"/api/v4/projects/{quote(project, safe='')}"
            f"/repository/files/{quote(path, safe='')}/raw",
            params=params,
            truncate=True,
        )
        return response.text, cut

    async def blame(
        self,
        project: str,
        path: str,
        *,
        ref: str | None,
        line_from: int | None,
        line_to: int | None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        if line_from is not None:
            params["range[start]"] = line_from
        if line_to is not None:
            params["range[end]"] = line_to
        response, _ = await self._get(
            f"/api/v4/projects/{quote(project, safe='')}"
            f"/repository/files/{quote(path, safe='')}/blame",
            params=params or None,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise errors.UpstreamUnavailable("gitlab blame returned non-JSON content") from exc
        if not isinstance(payload, list):
            raise errors.UpstreamUnavailable("gitlab blame results have an unexpected format")
        return [item for item in payload if isinstance(item, dict)]


class GitLabConnector:
    name = "gitlab"

    def probe_guard(self) -> Decision:
        return gitlab_guard.check_gitlab("GET", "/api/v4/user")

    def create_client(self, target: Target) -> _GitLabClient:
        return _GitLabClient(target)

    async def probe(self, client: _GitLabClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _GitLabClient) -> None:
        return None

    async def search_code(
        self,
        client: _GitLabClient,
        target: Target,
        *,
        project: str,
        query: str,
        ref: str | None,
        limit: int,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        return await client.search_code(
            project, query, ref=ref, per_page=limit, page=page
        )

    async def get_file(
        self,
        client: _GitLabClient,
        target: Target,
        *,
        project: str,
        path: str,
        ref: str | None,
    ) -> tuple[str, bool]:
        return await client.get_file(project, path, ref=ref)

    async def blame(
        self,
        client: _GitLabClient,
        target: Target,
        *,
        project: str,
        path: str,
        ref: str | None,
        line_from: int | None,
        line_to: int | None,
    ) -> list[dict[str, Any]]:
        return await client.blame(
            project, path, ref=ref, line_from=line_from, line_to=line_to
        )


connector = GitLabConnector()
