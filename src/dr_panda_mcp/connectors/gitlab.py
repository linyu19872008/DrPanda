"""GitLab 最小只读连接器：读取当前用户（只发 GET）。"""

from __future__ import annotations

import httpx

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import gitlab as gitlab_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _GitLabClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        options = self.target.options
        base_url = options.get("base_url", "").rstrip("/")
        if not base_url:
            raise errors.UpstreamUnavailable("gitlab 目标没有配置 base_url")
        client = httpx.AsyncClient(
            base_url=base_url,
            headers={"PRIVATE-TOKEN": self.target.secret.get("token", "")},
            timeout=base.timeout_seconds(self.target),
        )
        try:
            response = await client.get("/api/v4/user")
            base.check_http_response(response, "gitlab")
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"gitlab 探测失败：{exc}") from exc
        finally:
            await client.aclose()


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


connector = GitLabConnector()
