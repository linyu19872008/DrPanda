"""Kafka 只读连接器：消费组滞后、分区位点、单分区有限拉取。

不使用消费组：``AIOKafkaConsumer`` 一律 ``group_id=None``、关闭自动提交，
只用 ``assign + seek`` 拉取；不创建生产者，也不提交 offset。
"""

from __future__ import annotations

from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import kafka as kafka_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return base.to_jsonable(value)


class _KafkaClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _kwargs(self) -> dict[str, Any]:
        options = self.target.options
        servers = options.get("bootstrap_servers")
        if isinstance(servers, str):
            servers = [part.strip() for part in servers.split(",") if part.strip()]
        if not servers:
            raise errors.UpstreamUnavailable("kafka 目标没有配置 bootstrap_servers")
        protocol = str(options.get("security_protocol", "PLAINTEXT"))
        kwargs: dict[str, Any] = {
            "bootstrap_servers": servers,
            "request_timeout_ms": int(base.timeout_seconds(self.target) * 1000),
            "security_protocol": protocol,
        }
        if protocol in {"SSL", "SASL_SSL"}:
            ca_pem = str(options.get("ca_pem") or "").strip()
            cert = self.target.secret.get("client_cert", "")
            key = self.target.secret.get("client_key", "")
            if ca_pem or cert or key:
                kwargs["ssl_context"] = base.build_tls_context(
                    ca_pem=ca_pem,
                    client_cert=cert,
                    client_key=key,
                )
        elif options.get("ca_pem") or self.target.secret.get("client_cert"):
            raise errors.UpstreamUnavailable(
                "kafka TLS 材料只允许用于 SSL / SASL_SSL"
            )
        if protocol.startswith("SASL"):
            mechanism = str(options.get("sasl_mechanism") or "").strip()
            user = str(options.get("sasl_user") or "").strip()
            password = self.target.secret.get("sasl_password", "")
            if not mechanism or not user or not password:
                raise errors.UpstreamUnavailable(
                    "kafka SASL 协议缺少机制、用户或密码"
                )
            kwargs["sasl_mechanism"] = mechanism
            kwargs["sasl_plain_username"] = user
            kwargs["sasl_plain_password"] = password
        return kwargs

    def _consumer(self):
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(errors.missing_client_message("kafka")) from exc
        return AIOKafkaConsumer(
            group_id=None,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            **self._kwargs(),
        )

    def _admin(self):
        try:
            from aiokafka.admin import AIOKafkaAdminClient
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(errors.missing_client_message("kafka")) from exc
        return AIOKafkaAdminClient(**self._kwargs())

    async def ping(self) -> None:
        admin = self._admin()
        try:
            await admin.start()
            await admin.describe_cluster()
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"kafka 探测失败：{exc}") from exc
        finally:
            await admin.close()

    async def lag(self, group: str, topic: str | None) -> list[dict[str, Any]]:
        admin = self._admin()
        try:
            await admin.start()
            offsets = await admin.list_consumer_group_offsets(group)
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"kafka 消费组读取失败：{exc}") from exc
        finally:
            await admin.close()

        partitions = [
            tp for tp in offsets if topic is None or tp.topic == topic
        ]
        if not partitions:
            return []
        consumer = self._consumer()
        try:
            await consumer.start()
            high = await consumer.end_offsets(partitions)
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"kafka 位点读取失败：{exc}") from exc
        finally:
            await consumer.stop()

        rows: list[dict[str, Any]] = []
        for tp in partitions:
            meta = offsets[tp]
            committed = getattr(meta, "offset", meta)
            high_offset = high.get(tp)
            lag = max(int(high_offset or 0) - int(committed or 0), 0)
            rows.append(
                {
                    "group": group,
                    "topic": tp.topic,
                    "partition": tp.partition,
                    "committed": committed,
                    "high": high_offset,
                    "lag": lag,
                }
            )
        return sorted(rows, key=lambda row: (row["topic"], row["partition"]))

    async def offsets(self, topic: str) -> list[dict[str, Any]]:
        consumer = self._consumer()
        try:
            await consumer.start()
            partition_ids = sorted(consumer.partitions_for_topic(topic) or [])
            if not partition_ids:
                raise errors.UpstreamNotFound(f"topic {topic} 不存在或没有分区")
            from aiokafka import TopicPartition

            partitions = [TopicPartition(topic, partition) for partition in partition_ids]
            low = await consumer.beginning_offsets(partitions)
            high = await consumer.end_offsets(partitions)
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"kafka 位点读取失败：{exc}") from exc
        finally:
            await consumer.stop()
        return [
            {
                "topic": tp.topic,
                "partition": tp.partition,
                "low": low.get(tp),
                "high": high.get(tp),
            }
            for tp in partitions
        ]

    async def peek(
        self,
        topic: str,
        partition: int,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        consumer = self._consumer()
        try:
            from aiokafka import TopicPartition

            tp = TopicPartition(topic, partition)
            await consumer.start()
            partition_ids = consumer.partitions_for_topic(topic) or set()
            if partition not in partition_ids:
                raise errors.UpstreamNotFound(f"topic {topic} 没有分区 {partition}")
            low = (await consumer.beginning_offsets([tp]))[tp]
            high = (await consumer.end_offsets([tp]))[tp]
            if offset < low:
                raise errors.GuardRejected(
                    f"offset {offset} 早于分区 low watermark {low}",
                    code=errors.DANGEROUS_OPERATION,
                )
            if offset >= high:
                return []
            effective = min(limit, int(high) - offset)
            consumer.assign([tp])
            consumer.seek(tp, offset)
            batches = await consumer.getmany(
                tp, timeout_ms=int(base.timeout_seconds(self.target) * 1000), max_records=effective
            )
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"kafka 拉取失败：{exc}") from exc
        finally:
            await consumer.stop()

        rows: list[dict[str, Any]] = []
        for records in batches.values():
            for record in records[:effective]:
                rows.append(
                    {
                        "topic": record.topic,
                        "partition": record.partition,
                        "offset": record.offset,
                        "timestamp": record.timestamp,
                        "key": _decode(record.key),
                        "value": _decode(record.value),
                        "headers": base.to_jsonable(getattr(record, "headers", [])),
                    }
                )
        return rows


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

    async def lag(
        self,
        client: _KafkaClient,
        target: Target,
        *,
        group: str,
        topic: str | None,
    ) -> list[dict[str, Any]]:
        return await client.lag(group, topic)

    async def offsets(
        self, client: _KafkaClient, target: Target, *, topic: str
    ) -> list[dict[str, Any]]:
        return await client.offsets(topic)

    async def peek(
        self,
        client: _KafkaClient,
        target: Target,
        *,
        topic: str,
        partition: int,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await client.peek(topic, partition, offset, limit)


connector = KafkaConnector()
