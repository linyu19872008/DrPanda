"""CLS 最小只读连接器：列出日志集（只读描述）。"""

from __future__ import annotations

import asyncio

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import cls as cls_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _CLSClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        try:
            from tencentcloud.cls.v20201016 import cls_client, models
            from tencentcloud.common import credential
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "cls 客户端未安装：uv sync --extra cls"
            ) from exc

        options = self.target.options
        secrets = self.target.secret
        timeout = base.timeout_seconds(self.target)

        def _call() -> None:
            cred = credential.Credential(
                secrets.get("secret_id", ""), secrets.get("secret_key", "")
            )
            client = cls_client.ClsClient(
                cred, options.get("region", ""), timeout=int(timeout)
            )
            client.DescribeLogsets(models.DescribeLogsetsRequest())

        try:
            await asyncio.to_thread(_call)
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"cls 探测失败：{exc}") from exc


class CLSConnector:
    name = "cls"

    def probe_guard(self) -> Decision:
        return cls_guard.check_cls("describe_logsets", {})

    def create_client(self, target: Target) -> _CLSClient:
        return _CLSClient(target)

    async def probe(self, client: _CLSClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _CLSClient) -> None:
        return None


connector = CLSConnector()
