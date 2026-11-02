"""CLS 只读连接器：列出日志集、检索日志、读取日志上下文。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from dr_panda_mcp import errors
from dr_panda_mcp.connectors import base
from dr_panda_mcp.guards import cls as cls_guard
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target


def topic_id(topic: str) -> str:
    """登记的 topic 可以是 ``日志集/topic``；CLS API 需要最后一段 TopicId。"""
    return topic.rsplit("/", 1)[-1].strip()


def _time_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).isoformat(timespec="seconds")
    return str(value)


def _btime_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # CLS DescribeLogContext 要求 UTC+8 的 "YYYY-mm-dd HH:MM:SS.FFF"。
        return datetime.fromtimestamp(value, tz=timezone(timedelta(hours=8))).strftime(
            "%Y-%m-%d %H:%M:%S.000"
        )
    return str(value)


class _CLSClient:
    def __init__(self, target: Target) -> None:
        self.target = target

    def _sdk(self):
        try:
            from tencentcloud.cls.v20201016 import cls_client, models
            from tencentcloud.common import credential
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise errors.UpstreamUnavailable(
                "cls 客户端未安装：uv sync --extra cls"
            ) from exc
        options = self.target.options
        secrets = self.target.secret
        credential_obj = credential.Credential(
            secrets.get("secret_id", ""), secrets.get("secret_key", "")
        )
        client = cls_client.ClsClient(
            credential_obj,
            options.get("region", ""),
            timeout=int(base.timeout_seconds(self.target)),
        )
        return client, models

    async def ping(self) -> None:
        client, models = self._sdk()

        def _call() -> None:
            client.DescribeLogsets(models.DescribeLogsetsRequest())

        try:
            await asyncio.to_thread(_call)
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"cls 探测失败：{exc}") from exc

    async def search_log(
        self,
        *,
        topic: str,
        query: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        client, models = self._sdk()

        def _call():
            request = models.SearchLogRequest()
            request.TopicId = topic_id(topic)
            request.Query = query
            request.From = int(start.timestamp())
            request.To = int(end.timestamp())
            request.Limit = limit
            request.Sort = "desc"
            return client.SearchLog(request)

        try:
            response = await asyncio.to_thread(_call)
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"cls 检索失败：{exc}") from exc

        rows: list[dict[str, Any]] = []
        for item in getattr(response, "Results", None) or []:
            rows.append(
                {
                    "time": _time_text(getattr(item, "Time", None)),
                    "btime": _btime_text(
                        getattr(item, "BTime", None) or getattr(item, "Time", None)
                    ),
                    "topic": topic,
                    "package_id": getattr(item, "PkgId", None),
                    "package_log_id": getattr(item, "PkgLogId", None),
                    "content": getattr(item, "Log", "")
                    or getattr(item, "Content", ""),
                }
            )
        return rows

    async def describe_context(
        self,
        *,
        topic: str,
        log_id: str,
        btime: str,
        pkg_log_id: int,
        before: int,
        after: int,
    ) -> list[dict[str, Any]]:
        client, models = self._sdk()

        def _call():
            request = models.DescribeLogContextRequest()
            request.TopicId = topic_id(topic)
            request.PkgId = log_id
            request.BTime = btime
            request.PkgLogId = pkg_log_id
            request.PrevLogs = before
            request.NextLogs = after
            return client.DescribeLogContext(request)

        try:
            response = await asyncio.to_thread(_call)
        except errors.DrPandaError:
            raise
        except Exception as exc:
            raise errors.UpstreamUnavailable(f"cls 上下文读取失败：{exc}") from exc

        items = (
            getattr(response, "LogContextInfos", None)
            or getattr(response, "ContextInfos", None)
            or getattr(response, "Results", None)
            or []
        )
        rows: list[dict[str, Any]] = []
        for item in items:
            rows.append(
                {
                    "time": _time_text(
                        getattr(item, "Time", None) or getattr(item, "BTime", None)
                    ),
                    "topic": topic,
                    "package_id": getattr(item, "PkgId", None),
                    "package_log_id": getattr(item, "PkgLogId", None),
                    "btime": _btime_text(
                        getattr(item, "BTime", None)
                        or getattr(item, "Time", None)
                    ),
                    "content": getattr(item, "Content", "")
                    or getattr(item, "Log", ""),
                }
            )
        return rows


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

    async def search_log(
        self,
        client: _CLSClient,
        target: Target,
        *,
        topic: str,
        query: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        return await client.search_log(
            topic=topic, query=query, start=start, end=end, limit=limit
        )

    async def describe_context(
        self,
        client: _CLSClient,
        target: Target,
        *,
        topic: str,
        log_id: str,
        btime: str,
        pkg_log_id: int,
        before: int,
        after: int,
    ) -> list[dict[str, Any]]:
        return await client.describe_context(
            topic=topic,
            log_id=log_id,
            btime=btime,
            pkg_log_id=pkg_log_id,
            before=before,
            after=after,
        )


connector = CLSConnector()
