"""DrPanda MCP 进程入口（planning 3.2 启动序列）。

读环境变量 → 预检端口 → 创建运行时（引擎、迁移、密钥、仓储）→ 启动 uvicorn。
配置或启动失败返回退出码 2，并在 stderr 给出可操作的原因。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from dataclasses import replace

import uvicorn

from dr_panda_mcp import auth
from dr_panda_mcp.audit import run_cleanup_loop
from dr_panda_mcp.config import Config, is_loopback_host, load_config
from dr_panda_mcp.errors import ConfigError, StartupError
from dr_panda_mcp.install import load_install_state
from dr_panda_mcp.runtime import create_runtime
from dr_panda_mcp.server import SERVER_NAME, check_port_available, create_app
from dr_panda_mcp.setup import SetupApp

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
    if not is_loopback_host(config.host):
        if not config.allow_remote:
            raise StartupError(
                "当前只允许监听 127.0.0.1 / ::1 / localhost；"
                "远程访问需显式设置 DR_PANDA_ALLOW_REMOTE=1、HTTPS 反向代理和 DR_PANDA_PUBLIC_URL"
            )
        if not config.public_url or not config.public_url.startswith("https://"):
            raise StartupError("远程访问必须配置 HTTPS 的 DR_PANDA_PUBLIC_URL")
    check_port_available(config.host, config.port)
    install_state = load_install_state(config.install_file, config.install_key_file)
    if install_state is None and not is_loopback_host(config.host):
        raise StartupError("首次安装必须在 127.0.0.1 / localhost 完成，完成后再启用远程监听")
    runtime = None
    cleanup_task = None
    if install_state is not None:
        config = replace(config, database_url=install_state.database_url)
        runtime = await create_runtime(config)
        if not await auth.has_admin(runtime.session_factory):
            await runtime.close()
            raise StartupError("安装状态存在但配置库没有管理员，请恢复备份或使用恢复命令")
        cleanup_task = asyncio.create_task(run_cleanup_loop(runtime))
        app = create_app(config, runtime, auth_required=True)
    else:
        app = SetupApp(config)
    try:
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
        if cleanup_task is not None:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        if runtime is not None:
            await runtime.close()
        elif isinstance(app, SetupApp):
            await app.close()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _fail(message: str) -> None:
    print(f"dr-panda-mcp: {message}", file=sys.stderr)
