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


async def cleanup_once(runtime: Runtime) -> int:
    """执行一轮清理，返回删除条数。"""
    current = await settings_module.load(runtime.store)
    started = time.perf_counter()
    deleted = await runtime.store.cleanup_audit(current.audit_retention_days)
    if deleted:
        logger.info(
            format_event(
                "audit.cleanup",
                f"保留 {current.audit_retention_days} 天",
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
            logger.warning(failure_text("store.error", "审计清理失败，下一轮重试"))
        if interval is not None:
            await asyncio.sleep(interval)
            continue
        try:
            current = await settings_module.load(runtime.store)
            delay = current.audit_cleanup_interval_minutes * 60
        except Exception:  # noqa: BLE001 - 读不到间隔时用默认值
            logger.warning(failure_text("store.error", "读取审计清理间隔失败，使用默认间隔"))
            delay = INTERVAL_SECONDS
        await asyncio.sleep(delay)
