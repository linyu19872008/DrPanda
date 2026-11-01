"""连接器公共设施：超时、行/字节截断、统一返回包络（planning 8.1 / 8.3）。

这里只放与具体组件无关的部分；各组件连接器实现"最小只读探测"。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as time_value
from decimal import Decimal
from typing import Any, Protocol, Self

from dr_panda_mcp import errors
from dr_panda_mcp.guards.protocol import Decision
from dr_panda_mcp.store.protocol import Target

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_ROWS = 100
DEFAULT_MAX_BYTES = 102_400


class Connector(Protocol):
    """一个排查组件的连接器。``name`` 与目标 type 一致。"""

    name: str

    def probe_guard(self) -> Decision:
        """测试连接要执行的最小只读操作，先过闸门。"""

    def create_client(self, target: Target) -> Any: ...

    async def probe(self, client: Any, target: Target) -> None: ...

    async def close_client(self, client: Any) -> None: ...


@dataclass(frozen=True)
class Truncation:
    reason: str
    limit: int

    def as_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "limit": self.limit}


def to_jsonable(value: Any) -> Any:
    """把驱动返回的日期、Decimal、bytes 等转成可 JSON 序列化的值。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, (datetime, date, time_value)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    return str(value)


def timeout_seconds(target: Target) -> float:
    value = target.options.get("timeout_s", DEFAULT_TIMEOUT_SECONDS)
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return float(DEFAULT_TIMEOUT_SECONDS)
    return min(max(seconds, 1.0), 120.0)


def max_rows(target: Target) -> int:
    value = target.options.get("max_rows", DEFAULT_MAX_ROWS)
    try:
        rows = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_ROWS
    return min(max(rows, 1), 1000)


def max_bytes(target: Target) -> int:
    value = target.options.get("max_bytes", DEFAULT_MAX_BYTES)
    try:
        size = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_BYTES
    return min(max(size, 4096), 1_048_576)


async def run_with_timeout(awaitable, seconds: float):
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except TimeoutError as exc:
        raise errors.UpstreamTimeout(f"上游调用超过 {seconds:.0f} 秒") from exc


def apply_row_limits(
    rows: list[dict[str, Any]], max_row_count: int, max_byte_count: int
) -> tuple[list[dict[str, Any]], Truncation | None]:
    """按行数与字节数截断；先触达者为准。"""
    kept: list[dict[str, Any]] = []
    used = 0
    for index, row in enumerate(rows):
        if index >= max_row_count:
            return kept, Truncation("rows", max_row_count)
        size = len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
        if used + size > max_byte_count:
            return kept, Truncation("bytes", max_byte_count)
        kept.append(row)
        used += size
    return kept, None


def build_envelope(
    target: Target,
    *,
    summary: str,
    elapsed_ms: int,
    rows: list[dict[str, Any]] | None = None,
    stats: dict[str, Any] | None = None,
    time_range: dict[str, str] | None = None,
    truncation: Truncation | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """成功结果的统一包络（planning 8.1 的 11 个顶层键）。"""
    result_rows = rows or []
    return {
        "target": target.name,
        "type": target.type,
        "summary": summary,
        "time_range": time_range,
        "returned": len(result_rows),
        "truncated": truncation is not None,
        "truncation": truncation.as_dict() if truncation else None,
        "elapsed_ms": elapsed_ms,
        "rows": result_rows,
        "stats": stats,
        "notes": list(notes or []),
    }


def check_http_response(response, component: str) -> None:
    """把上游 HTTP 状态映射成统一错误。"""
    if response.status_code < 400:
        return
    message = f"{component} 返回 HTTP {response.status_code}"
    if response.status_code == 404:
        raise errors.UpstreamNotFound(message)
    raise errors.UpstreamUnavailable(message)


class Stopwatch:
    """简单的毫秒计时器，用于包络里的 ``elapsed_ms``。"""

    def __init__(self) -> None:
        self._start = 0.0

    def __enter__(self) -> Self:
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)
