"""FastMCP 服务与 HTTP 应用装配（planning 3.1 / 3.5 / 9.2）。

M1 起由运行时提供配置库：``/healthz`` 会检查配置库连通性。
网页与 ``/mcp`` 共用同一个进程与端口，并共用 Host/Origin 校验。
"""

from __future__ import annotations

import errno
import logging
import socket
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from dr_panda_mcp import auth
from dr_panda_mcp.errors import StartupError
from dr_panda_mcp.prompts import register_prompts
from dr_panda_mcp.tools import register_tools
from dr_panda_mcp.web.auth_routes import register_auth_routes
from dr_panda_mcp.web.profile import register_profile_routes
from dr_panda_mcp.web.routes import register_web_routes
from dr_panda_mcp.web.security import (
    AuthMiddleware,
    CSRFMiddleware,
    NotFoundMiddleware,
    SecurityHeadersMiddleware,
)

if TYPE_CHECKING:
    from starlette.applications import Starlette

    from dr_panda_mcp.config import Config
    from dr_panda_mcp.runtime import Runtime

logger = logging.getLogger(__name__)

SERVER_NAME = "dr-panda-mcp"

# 服务器说明与 planning 8.8 的纪律一致；M3 起注册 tools 后仍复用这段文本。
SERVER_INSTRUCTIONS = (
    "Dr Panda MCP 是线上排查用的只读工具集。调用只接受 target 名，"
    "不接受主机、DSN、账号或密码。八个排查组件绝对只读，"
    "日志与搜索必须带时间窗，优先使用 trace id，"
    "拒绝全表扫描与无上限拉取，结果被截断时必须向用户说明。"
    "先调用 systems_status 了解已登记且启用的目标。"
)


def package_version() -> str:
    try:
        return version("dr-panda-mcp")
    except PackageNotFoundError:
        return "0.0.0"


def create_server(config: Config, runtime: Runtime) -> FastMCP:
    """构造 FastMCP 实例并注册 M1 的 HTTP 路由。"""
    server = FastMCP(
        name=SERVER_NAME,
        version=package_version(),
        instructions=SERVER_INSTRUCTIONS,
    )

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> JSONResponse:
        try:
            await runtime.store.ping()
        except Exception:
            logger.warning("健康检查失败：配置库不可用", exc_info=True)
            return JSONResponse(
                {"ok": False, "version": package_version(), "db": "error"},
                status_code=503,
            )
        return JSONResponse({"ok": True, "version": package_version(), "db": "ok"})

    register_tools(server, runtime)
    register_prompts(server)
    register_web_routes(server, runtime)
    return server


def create_app(
    config: Config,
    runtime: Runtime,
    *,
    auth_required: bool = True,
    session_key: bytes | None = None,
) -> Starlette:
    """返回同时提供配置网页与 ``/mcp`` 的 Starlette 应用。

    ``auth_required=False`` 只用于既有单元测试的隔离装配；生产入口始终启用认证。
    """
    server = create_server(config, runtime)
    if auth_required:
        key = session_key or auth.load_or_create_session_key(config.session_key_file)
        register_auth_routes(
            server,
            runtime,
            key,
            secure_cookies=bool(config.public_url and config.public_url.startswith("https://")),
        )
        register_profile_routes(server, runtime, config)
    allowed_hosts = None
    allowed_origins = None
    if config.public_url:
        from urllib.parse import urlsplit

        parsed = urlsplit(config.public_url)
        if parsed.netloc:
            allowed_hosts = [parsed.netloc]
            allowed_origins = [f"{parsed.scheme}://{parsed.netloc}"]
    app = server.http_app(
        path="/mcp",
        transport="http",
        host_origin_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )
    if not auth_required:
        return SecurityHeadersMiddleware(app)
    return SecurityHeadersMiddleware(
        NotFoundMiddleware(
            CSRFMiddleware(
                AuthMiddleware(
                    app,
                    runtime=runtime,
                    session_key=key or b"",
                    auth_required=True,
                )
            )
        )
    )


def check_port_available(host: str, port: int) -> None:
    """预检端口，占用或无法监听时抛出带处理建议的 ``StartupError``。"""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise StartupError(
                f"端口 {port} 已被占用，请用 DR_PANDA_PORT 换一个端口"
            ) from exc
        raise StartupError(
            f"无法监听 {host}:{port}（{exc.strerror}），请检查 DR_PANDA_HOST / DR_PANDA_PORT"
        ) from exc
    finally:
        sock.close()
