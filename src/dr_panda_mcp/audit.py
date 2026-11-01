"""审计维护：按保留期清理过期记录（planning 9.6）。

清理只记日志、不写审计，避免审计表自增；保留天数每轮从系统配置读取。
"""

from __future__ import annotations

import asyncio
import logging

from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.runtime import Runtime

logger = logging.getLogger(__name__)

INITIAL_DELAY_SECONDS = 60.0
INTERVAL_SECONDS = 3600.0


async def cleanup_once(runtime: Runtime) -> int:
    """执行一轮清理，返回删除条数。"""
    current = await settings_module.load(runtime.store)
    deleted = await runtime.store.cleanup_audit(current.audit_retention_days)
    if deleted:
        logger.info(
            "audit.cleanup：删除 %d 条超过 %d 天的审计",
            deleted,
            current.audit_retention_days,
        )
    return deleted


async def run_cleanup_loop(
    runtime: Runtime,
    *,
    initial_delay: float = INITIAL_DELAY_SECONDS,
    interval: float = INTERVAL_SECONDS,
) -> None:
    """启动后稍等再首跑，之后固定间隔执行；进程退出时取消。"""
    await asyncio.sleep(initial_delay)
    while True:
        try:
            await cleanup_once(runtime)
        except Exception:
            logger.warning("审计清理失败，下一轮重试", exc_info=True)
        await asyncio.sleep(interval)
