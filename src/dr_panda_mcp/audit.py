"""审计维护：按保留期清理过期记录（planning 9.6）。

清理只记日志、不写审计，避免审计表自增；保留天数每轮从系统配置读取。
"""

from __future__ import annotations

import asyncio
import logging
import time

from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.log import failure_text, format_event
from dr_panda_mcp.runtime import Runtime

logger = logging.getLogger(__name__)

INITIAL_DELAY_SECONDS = 60.0
INTERVAL_SECONDS = 3600.0
SLEEP_SLICE_SECONDS = 60.0


async def cleanup_once(runtime: Runtime) -> int:
    """执行一轮清理，返回删除条数。"""
    current = await settings_module.load(runtime.store)
    started = time.perf_counter()
    deleted = await runtime.store.cleanup_audit(
        current.audit_retention_days,
        batch_size=current.audit_cleanup_batch_size,
        max_seconds=float(current.audit_cleanup_max_seconds),
    )
    if deleted:
        logger.info(
            format_event(
                "audit.cleanup",
                f"retention {current.audit_retention_days} days",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                returned=deleted,
            )
        )
    return deleted


async def run_cleanup_loop(
    runtime: Runtime,
    *,
    initial_delay: float = INITIAL_DELAY_SECONDS,
    interval: float | None = None,
) -> None:
    """启动后稍等再首跑；未显式指定 interval 时每轮读取系统配置。"""
    await asyncio.sleep(initial_delay)
    while True:
        try:
            await cleanup_once(runtime)
        except Exception:  # noqa: BLE001 - 清理失败留到下一轮，不打断进程
            logger.warning(failure_text("store.error", "audit cleanup failed; retrying next round"))
        if interval is not None:
            await asyncio.sleep(interval)
            continue
        await _sleep_with_configured_interval(runtime)


async def _sleep_with_configured_interval(runtime: Runtime) -> None:
    """按系统配置睡眠；分片醒来，把改小间隔的生效延迟控制在 60 秒内。"""
    started = time.monotonic()
    delay = await _configured_interval(runtime)
    while True:
        elapsed = time.monotonic() - started
        if elapsed >= delay:
            return
        await asyncio.sleep(min(SLEEP_SLICE_SECONDS, delay - elapsed))
        delay = await _configured_interval(runtime)


async def _configured_interval(runtime: Runtime) -> float:
    try:
        current = await settings_module.load(runtime.store)
        return current.audit_cleanup_interval_minutes * 60
    except Exception:  # noqa: BLE001 - 读不到间隔时用默认值
        logger.warning(failure_text("store.error", "failed to read the audit cleanup interval; using the default"))
        return INTERVAL_SECONDS
