"""Kafka 最小只读连接器：描述集群元数据（不加入消费组）。"""

from __future__ import annotations

from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import kafka as kafka_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


class _KafkaClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    async def ping(self) -> None:
        try:
            from aiokafka.admin import AIOKafkaAdminClient
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "kafka 客户端未安装：uv sync --extra kafka"
            ) from exc

        options = self.target.options
        servers = options.get("bootstrap_servers")
        if isinstance(servers, str):
            servers = [part.strip() for part in servers.split(",") if part.strip()]
        kwargs: dict[str, Any] = {
            "bootstrap_servers": servers or [],
            "request_timeout_ms": int(base.timeout_seconds(self.target) * 1000),
            "security_protocol": options.get("security_protocol", "PLAINTEXT"),
        }
        if options.get("sasl_mechanism"):
            kwargs["sasl_mechanism"] = options["sasl_mechanism"]
            kwargs["sasl_plain_username"] = options.get("sasl_user", "")
            kwargs["sasl_plain_password"] = self.target.secret.get(
                "sasl_password", ""
            )

        client = AIOKafkaAdminClient(**kwargs)
        try:
            await client.start()
            await client.describe_cluster()
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"kafka 探测失败：{exc}") from exc
        finally:
            await client.close()


class KafkaConnector:
    name = "kafka"

    def probe_guard(self) -> Decision:
        return kafka_guard.check_kafka("describe_cluster", {})

    def create_client(self, target: Target) -> _KafkaClient:
        return _KafkaClient(target)

    async def probe(self, client: _KafkaClient, target: Target) -> None:
        await client.ping()

    async def close_client(self, client: _KafkaClient) -> None:
        return None


connector = KafkaConnector()
