"""Dr Panda MCP 进程入口（planning 3.2 启动序列）。

读环境变量 → 预检端口 → 创建运行时（引擎、迁移、密钥、仓储）→ 启动 uvicorn。
配置或启动失败返回退出码 2，并在 stderr 给出可操作的原因。
"""

from __future__ import annotations

import asyncio
import logging
import sys

import uvicorn

from dr_panda_mcp.config import Config, load_config
from dr_panda_mcp.errors import ConfigError, StartupError
from dr_panda_mcp.runtime import create_runtime
from dr_panda_mcp.server import SERVER_NAME, check_port_available, create_app

logger = logging.getLogger(__name__)


def main() -> int:
    """控制台入口。返回进程退出码：0 正常，2 配置或启动失败。"""
    try:
        config = load_config()
    except ConfigError as exc:
        _fail(f"启动失败：{exc}")
        return 2

    _configure_logging(config.log_level)
    logger.info(
        "配置就绪：host=%s port=%d database=%s",
        config.host,
        config.port,
        config.database_url,
    )

    try:
        return asyncio.run(_run(config))
    except StartupError as exc:
        _fail(f"启动失败：{exc}")
        return 2
    except KeyboardInterrupt:
        return 0


async def _run(config: Config) -> int:
    check_port_available(config.host, config.port)
    runtime = await create_runtime(config)
    try:
        app = create_app(config, runtime)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=config.host,
                port=config.port,
                log_level=config.log_level.lower(),
            )
        )
        logger.info(
            "%s 启动：http://%s:%d（/mcp 与配置网页共用）",
            SERVER_NAME,
            config.host,
            config.port,
        )
        await server.serve()
        return 0
    finally:
        await runtime.close()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _fail(message: str) -> None:
    print(f"dr-panda-mcp: {message}", file=sys.stderr)
