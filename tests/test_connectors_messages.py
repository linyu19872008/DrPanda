from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import kafka as kafka_module
from dr_panda_mcp.connectors import rabbit as rabbit_module
from dr_panda_mcp.store.protocol import Target
from tests.fakes import make_target


def _rabbit_target() -> Target:
    return make_target(
        type_="rabbitmq",
        options={
            "management_url": "http://rabbit:15672",
            "user": "ro",
            "allowed_vhosts": ["/", "pay"],
            "timeout_s": "15",
        },
        secret={"password": "pw"},
    )


async def test_rabbit_queues_and_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    client = rabbit_module.connector.create_client(_rabbit_target())
    calls: list[str] = []

    async def fake_get(path: str):
        calls.append(path)
        if path == "/api/queues/pay":
            return [
                {
                    "name": "orders",
                    "vhost": "pay",
                    "messages": 2,
                    "messages_unacknowledged": 1,
                    "consumers": 1,
                    "state": "running",
                }
            ]
        if path.startswith("/api/queues/pay/orders"):
            return {"name": "orders", "vhost": "pay", "messages": 2, "durable": True}
        return []

    monkeypatch.setattr(client, "_get", fake_get)

    queues = await client.queues("pay")
    detail = await client.queue("pay", "orders")

    assert queues[0]["name"] == "orders"
    assert detail["durable"] is True
    assert calls == ["/api/queues/pay", "/api/queues/pay/orders"]


class _TP:
    def __init__(self, topic: str, partition: int) -> None:
        self.topic = topic
        self.partition = partition

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _TP) and (self.topic, self.partition) == (
            other.topic,
            other.partition,
        )

    def __hash__(self) -> int:
        return hash((self.topic, self.partition))


class _FakeConsumer:
    instances: ClassVar[list[_FakeConsumer]] = []

    def __init__(self, *topics: str, **kwargs: Any) -> None:
        self.topics = topics
        self.kwargs = kwargs
        self.assigned: list[_TP] = []
        self.seeks: list[tuple[_TP, int]] = []
        self.commits: list[int] = []
        _FakeConsumer.instances.append(self)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def partitions_for_topic(self, topic: str) -> set[int]:
        return {0, 1}

    async def beginning_offsets(self, partitions):
        return {tp: 5 for tp in partitions}

    async def end_offsets(self, partitions):
        return {tp: 100 for tp in partitions}

    def assign(self, partitions) -> None:
        self.assigned = list(partitions)

    def seek(self, tp, offset) -> None:
        self.seeks.append((tp, offset))

    async def getmany(self, *partitions, timeout_ms=None, max_records=None):
        tp = partitions[0]
        return {
            tp: [
                SimpleNamespace(
                    topic=tp.topic,
                    partition=tp.partition,
                    offset=self.seeks[-1][1],
                    timestamp=1767229200000,
                    key=b"k",
                    value=b"payload",
                    headers=[],
                )
            ]
        }

    async def commit(self) -> None:
        self.commits.append(1)


class _FakeAdmin:
    instances: ClassVar[list[_FakeAdmin]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        _FakeAdmin.instances.append(self)

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def describe_cluster(self) -> dict:
        return {}

    async def list_consumer_group_offsets(self, group: str):
        return {_TP("orders", 0): SimpleNamespace(offset=90)}


def _install_aiokafka(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeConsumer.instances.clear()
    _FakeAdmin.instances.clear()
    aiokafka = types.ModuleType("aiokafka")
    aiokafka.AIOKafkaConsumer = _FakeConsumer
    aiokafka.TopicPartition = _TP
    admin = types.ModuleType("aiokafka.admin")
    admin.AIOKafkaAdminClient = _FakeAdmin
    monkeypatch.setitem(sys.modules, "aiokafka", aiokafka)
    monkeypatch.setitem(sys.modules, "aiokafka.admin", admin)


def _kafka_target() -> Target:
    return make_target(
        type_="kafka",
        options={
            "bootstrap_servers": ["kafka:9092"],
            "security_protocol": "PLAINTEXT",
            "allowed_topics": ["orders"],
            "timeout_s": "15",
        },
    )


async def test_kafka_lag_and_offsets(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_aiokafka(monkeypatch)
    client = kafka_module.connector.create_client(_kafka_target())

    rows = await client.lag("g1", "orders")
    offsets = await client.offsets("orders")

    assert rows == [
        {"group": "g1", "topic": "orders", "partition": 0, "committed": 90, "high": 100, "lag": 10}
    ]
    assert offsets == [
        {"topic": "orders", "partition": 0, "low": 5, "high": 100},
        {"topic": "orders", "partition": 1, "low": 5, "high": 100},
    ]
    consumer = _FakeConsumer.instances[0]
    assert consumer.kwargs["group_id"] is None
    assert consumer.kwargs["enable_auto_commit"] is False
    assert consumer.commits == []
    assert _FakeAdmin.instances[0].closed is True


async def test_kafka_peek_is_assigned_and_seeked(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_aiokafka(monkeypatch)
    client = kafka_module.connector.create_client(_kafka_target())

    rows = await client.peek("orders", 0, 10, 20)

    assert rows[0]["value"] == "payload"
    consumer = _FakeConsumer.instances[0]
    assert consumer.assigned[0].topic == "orders"
    assert consumer.seeks == [(_TP("orders", 0), 10)]
    assert consumer.commits == []


async def test_kafka_peek_below_low_watermark(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_aiokafka(monkeypatch)
    client = kafka_module.connector.create_client(_kafka_target())

    with pytest.raises(errors.GuardRejected) as excinfo:
        await client.peek("orders", 0, 1, 10)

    assert excinfo.value.code == errors.DANGEROUS_OPERATION
