"""消息面：RabbitMQ 与 Kafka 五个只读工具（planning 8.6）。"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from fastmcp import FastMCP

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base as connectors_base
from dr_panda_mcp.connectors import get_connector
from dr_panda_mcp.guards import kafka as kafka_guard
from dr_panda_mcp.guards import rabbit as rabbit_guard
from dr_panda_mcp.guards.protocol import require
from dr_panda_mcp.runtime import Runtime
from dr_panda_mcp.store.protocol import Target
from dr_panda_mcp.tools.base import (
    TOOL_ANNOTATIONS,
    clamp_limit,
    finish,
    run_tool,
    trim_rows,
)


def _allowed(target: Target, key: str) -> list[str]:
    return [str(item) for item in target.options.get(key, [])]


def ensure_vhost(target: Target, vhost: str) -> str:
    allowed = _allowed(target, "allowed_vhosts")
    value = (vhost or "").strip()
    if not value:
        raise errors.InvalidArgument("必须指定 vhost")
    if not allowed:
        raise errors.ScopeDenied(f"目标 {target.name} 没有授权任何 vhost")
    if value not in allowed:
        raise errors.ScopeDenied(f"vhost {value} 不在目标 {target.name} 的授权范围内")
    return value


def ensure_topic(target: Target, topic: str) -> str:
    allowed = _allowed(target, "allowed_topics")
    value = (topic or "").strip()
    if not allowed:
        raise errors.ScopeDenied(f"目标 {target.name} 没有授权任何 topic")
    if not value:
        raise errors.InvalidArgument("必须指定 topic")
    if value not in allowed:
        raise errors.ScopeDenied(f"topic {value} 不在目标 {target.name} 的授权范围内")
    return value


def register_message_tools(server: FastMCP, runtime: Runtime) -> None:
    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def rabbit_queues(target: str, vhost: str = "") -> dict[str, Any]:
        """列出授权 vhost 的队列（消息数、未确认、消费者）。"""
        params = {"vhost": vhost or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            allowed = _allowed(tgt, "allowed_vhosts")
            if not allowed:
                raise errors.ScopeDenied(f"目标 {tgt.name} 没有授权任何 vhost")
            vhosts = [ensure_vhost(tgt, vhost)] if vhost else allowed
            cap = connectors_base.max_rows(tgt)
            connector = get_connector("rabbitmq")
            client = await runtime.catalog.client(tgt, connector)
            rows: list[dict[str, Any]] = []
            truncated = False
            for index, name in enumerate(vhosts):
                if len(rows) >= cap:
                    truncated = index < len(vhosts)
                    break
                path = f"/api/queues/{quote(name, safe='')}"
                require(rabbit_guard.check_rabbit("GET", path))
                items = await connector.queues(client, tgt, vhost=name)
                for item in items:
                    rows.append(
                        {
                            "queue": item.get("name"),
                            "vhost": item.get("vhost"),
                            "messages": item.get("messages"),
                            "unacked": item.get("messages_unacknowledged"),
                            "consumers": item.get("consumers"),
                            "state": item.get("state"),
                        }
                    )
            truncated = truncated or len(rows) > cap
            return finish(
                tgt,
                summary=f"GET /api/queues vhosts={len(vhosts)}",
                started=started,
                rows=rows[:cap],
                stats={"vhosts": vhosts},
                truncation=connectors_base.Truncation("rows", cap) if truncated else None,
            )

        return await run_tool(
            runtime, tool="rabbit_queues", name=target, target_type="rabbitmq",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def rabbit_queue(target: str, vhost: str, queue: str) -> dict[str, Any]:
        """查看单个队列的详情。"""
        params = {"vhost": vhost, "queue": queue}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_vhost(tgt, vhost)
            if not queue.strip():
                raise errors.InvalidArgument("queue 不能为空")
            path = f"/api/queues/{quote(chosen, safe='')}/{quote(queue, safe='')}"
            require(rabbit_guard.check_rabbit("GET", path))
            connector = get_connector("rabbitmq")
            client = await runtime.catalog.client(tgt, connector)
            item = await connector.queue(client, tgt, vhost=chosen, queue=queue)
            row = {
                "queue": item.get("name"),
                "vhost": item.get("vhost"),
                "messages": item.get("messages"),
                "unacked": item.get("messages_unacknowledged"),
                "consumers": item.get("consumers"),
                "state": item.get("state"),
                "durable": item.get("durable"),
                "arguments": item.get("arguments"),
            }
            return finish(
                tgt,
                summary=f"GET /api/queues/{chosen}/{queue}",
                started=started,
                rows=[row],
                stats={"vhost": chosen, "queue": queue},
            )

        return await run_tool(
            runtime, tool="rabbit_queue", name=target, target_type="rabbitmq",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def kafka_lag(
        target: str, group: str, topic: str = ""
    ) -> dict[str, Any]:
        """查看消费组在各分区的位点与滞后。"""
        params = {"group": group, "topic": topic or None}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            if not group.strip():
                raise errors.InvalidArgument("group 不能为空")
            topics = [ensure_topic(tgt, topic)] if topic else _allowed(tgt, "allowed_topics")
            if not topics:
                raise errors.ScopeDenied(f"目标 {tgt.name} 没有授权任何 topic")
            require(kafka_guard.check_kafka("describe_consumer_groups", {}))
            cap = connectors_base.max_rows(tgt)
            connector = get_connector("kafka")
            client = await runtime.catalog.client(tgt, connector)
            rows: list[dict[str, Any]] = []
            truncated = False
            for index, name in enumerate(topics):
                if len(rows) >= cap:
                    truncated = index < len(topics)
                    break
                rows.extend(await connector.lag(client, tgt, group=group, topic=name))
            truncated = truncated or len(rows) > cap
            return finish(
                tgt,
                summary=f"Kafka lag group={group} topics={len(topics)}",
                started=started,
                rows=rows[:cap],
                stats={"group": group, "topics": topics},
                truncation=connectors_base.Truncation("rows", cap) if truncated else None,
            )

        return await run_tool(
            runtime, tool="kafka_lag", name=target, target_type="kafka",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def kafka_offsets(target: str, topic: str) -> dict[str, Any]:
        """查看 topic 各分区的 low / high watermark。"""
        params = {"topic": topic}

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_topic(tgt, topic)
            require(kafka_guard.check_kafka("list_offsets", {}))
            connector = get_connector("kafka")
            client = await runtime.catalog.client(tgt, connector)
            rows = await connector.offsets(client, tgt, topic=chosen)
            return finish(
                tgt,
                summary=f"Kafka offsets topic={chosen}",
                started=started,
                rows=rows,
                stats={"topic": chosen},
            )

        return await run_tool(
            runtime, tool="kafka_offsets", name=target, target_type="kafka",
            params=params, handler=handler,
        )

    @server.tool(annotations=TOOL_ANNOTATIONS)
    async def kafka_peek(
        target: str,
        topic: str,
        partition: int,
        offset: int,
        limit: int = 10,
    ) -> dict[str, Any]:
        """从指定分区与 offset 起有限拉取消息（不加入消费组、不提交 offset）。"""
        params = {
            "topic": topic, "partition": partition, "offset": offset, "limit": limit,
        }

        async def handler(tgt: Target) -> dict[str, Any]:
            started = time.monotonic()
            chosen = ensure_topic(tgt, topic)
            if partition < 0:
                raise errors.InvalidArgument("partition 不能为负数")
            if offset < 0:
                raise errors.InvalidArgument("offset 不能为负数")
            cap = clamp_limit(limit or None, tgt, 10)
            require(
                kafka_guard.check_kafka(
                    "fetch",
                    {
                        "partition": partition,
                        "offset": offset,
                        "limit": cap,
                    },
                )
            )
            connector = get_connector("kafka")
            client = await runtime.catalog.client(tgt, connector)
            fetched = await connector.peek(
                client,
                tgt,
                topic=chosen,
                partition=partition,
                offset=offset,
                limit=cap + 1,
            )
            rows, truncation = trim_rows(fetched, cap)
            return finish(
                tgt,
                summary=f"Kafka peek {chosen}[{partition}]@{offset} limit={cap}",
                started=started,
                rows=rows,
                stats={"topic": chosen, "partition": partition, "offset": offset, "limit": cap},
                truncation=truncation,
            )

        return await run_tool(
            runtime, tool="kafka_peek", name=target, target_type="kafka",
            params=params, handler=handler,
        )
