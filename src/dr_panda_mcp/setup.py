"""首次安装向导（M7）：设置 admin 密码，选择配置库并完成初始化。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dr_panda_mcp import auth
from dr_panda_mcp import settings as settings_module
from dr_panda_mcp.audit import run_cleanup_loop
from dr_panda_mcp.config import Config
from dr_panda_mcp.errors import DrPandaError
from dr_panda_mcp.install import save_install_state
from dr_panda_mcp.log import RequestLogMiddleware
from dr_panda_mcp.runtime import Runtime, create_runtime
from dr_panda_mcp.server import create_app
from dr_panda_mcp.store.url import create_engine, ensure_driver, normalize_database_url
from dr_panda_mcp.web import assets, async_api, render, theme
from dr_panda_mcp.web.security import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


@dataclass
class SetupState:
    password_hash: str | None = None
    db_type: str = "sqlite"
    sqlite_path: str = "data/dr-panda.sqlite"
    host: str = "127.0.0.1"
    port: str = "3306"
    database: str = ""
    username: str = ""
    password: str = ""
    tested_url: str | None = None
    test_detail: str | None = None


class SetupApp:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = SetupState()
        self.normal_app = None
        self.runtime: Runtime | None = None
        self.cleanup_task: asyncio.Task | None = None
        self.app = Starlette(
            routes=[
                Route("/healthz", self.healthz, methods=["GET"]),
                Route("/mcp", self.mcp_unavailable, methods=["GET", "POST"]),
                Route("/", self.index, methods=["GET"]),
                Route("/setup", self.index, methods=["GET"]),
                Route("/setup/admin", self.admin_get, methods=["GET"]),
                Route("/setup/admin", self.admin_post, methods=["POST"]),
                Route("/setup/database", self.database_get, methods=["GET"]),
                Route("/setup/database", self.database_post, methods=["POST"]),
                Route("/setup/finish", self.finish, methods=["POST"]),
                Route("/language", self.language, methods=["POST"]),
                Route("/favicon.ico", self.favicon, methods=["GET"]),
                Mount("/static", StaticFiles(directory=STATIC_DIR), name="setup-static"),
            ]
        )
        self.app.add_middleware(SecurityHeadersMiddleware)
        self.app.add_middleware(RequestLogMiddleware)

    async def __call__(self, scope, receive, send) -> None:
        if self.normal_app is not None:
            await self.normal_app(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def close(self) -> None:
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        if self.runtime is not None:
            await self.runtime.close()

    async def favicon(self, request: Request) -> Response:
        return assets.icon_response(request)

    async def healthz(self, request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "installed": False})

    async def mcp_unavailable(self, request: Request) -> JSONResponse:
        return JSONResponse(
            {"error": "not_installed"}, status_code=503, headers={"Cache-Control": "no-store"}
        )

    async def index(self, request: Request) -> Response:
        if self.state.password_hash is None:
            return RedirectResponse("/setup/admin", status_code=303)
        return RedirectResponse("/setup/database", status_code=303)

    async def admin_get(self, request: Request) -> Response:
        if self.state.password_hash is not None:
            return RedirectResponse("/setup/database", status_code=303)
        return self._render("setup_admin.html", request)

    async def admin_post(self, request: Request) -> Response:
        form = await request.form()
        if not self._csrf_ok(request, form):
            return self._render("setup_admin.html", request, error="请求已过期，请重试", status=403)
        password = str(form.get("password", ""))
        confirm = str(form.get("confirm", ""))
        problem = auth.password_problem(password)
        if problem:
            return self._render("setup_admin.html", request, error=problem, status=400)
        if password != confirm:
            return self._render("setup_admin.html", request, error="两次输入的密码不一致", status=400)
        self.state.password_hash = auth.hash_password(password)
        return RedirectResponse("/setup/database", status_code=303)

    async def database_get(self, request: Request) -> Response:
        if self.state.password_hash is None:
            return RedirectResponse("/setup/admin", status_code=303)
        requested = request.query_params.get("db", "")
        if requested in {"sqlite", "mysql", "postgresql"} and requested != self.state.db_type:
            self.state.db_type = requested
            self.state.tested_url = None
            self.state.test_detail = None
            if requested == "mysql":
                self.state.port = "3306"
            elif requested == "postgresql":
                self.state.port = "5432"
        return self._render_database(request)

    async def database_post(self, request: Request) -> Response:
        if self.state.password_hash is None:
            return RedirectResponse("/setup/admin", status_code=303)
        form = await request.form()
        if not self._csrf_ok(request, form):
            return self._database_error(request, "请求已过期，请重试", status=403)
        self._capture_database(form)
        action = str(form.get("action", "test"))
        if action == "finish":
            return await self._finish_database(request)
        try:
            url = self._database_url()
            await _test_database(url)
        except Exception as exc:  # noqa: BLE001 - 安装页展示脱敏失败原因
            self.state.tested_url = None
            self.state.test_detail = None
            return self._database_error(request, _friendly_test_error(exc))
        self.state.tested_url = url
        self.state.test_detail = "连接成功"
        if async_api.wants_json(request):
            return async_api.ok(
                request, message="连接成功", data={"can_finish": True}
            )
        return self._render_database(request)

    def _database_error(
        self, request: Request, message: str, *, status: int = 400
    ) -> Response:
        if async_api.wants_json(request):
            return async_api.fail(
                request, async_api.CODE_BAD_REQUEST, message, status=status
            )
        return self._render_database(request, error=message, status=status)

    async def finish(self, request: Request) -> Response:
        form = await request.form()
        if not self._csrf_ok(request, form):
            return self._database_error(request, "请求已过期，请重试", status=403)
        self._capture_database(form)
        return await self._finish_database(request)

    async def _finish_database(self, request: Request) -> Response:
        if self.state.password_hash is None:
            return RedirectResponse("/setup/admin", status_code=303)
        try:
            url = self._database_url()
        except Exception as exc:  # noqa: BLE001
            return self._database_error(request, _friendly_test_error(exc))
        if self.state.tested_url != url:
            return self._database_error(request, "请先测试当前连接配置")
        cfg = replace(self.config, database_url=url)
        try:
            runtime = await create_runtime(cfg)
        except Exception as exc:
            logger.warning("安装迁移失败", exc_info=True)
            return self._database_error(request, _friendly_test_error(exc))
        try:
            if await auth.has_admin(runtime.session_factory):
                await runtime.close()
                return self._database_error(
                    request, "该配置库已有管理员，请使用已有安装登录"
                )
            user = await auth.create_admin(
                runtime.session_factory,
                password_hash=self.state.password_hash,
            )
            token = auth.generate_token()
            await auth.create_mcp_token(
                runtime.session_factory,
                user.id,
                name=None,
                token_hash=auth.hash_token(token),
                token_prefix=token[:12],
            )
            save_install_state(cfg.install_file, cfg.install_key_file, url)
        except Exception:
            await runtime.close()
            logger.warning("安装写入失败", exc_info=True)
            return self._database_error(request, "安装写入失败，请检查配置库权限")

        session_key = auth.load_or_create_session_key(cfg.session_key_file)
        user = await auth.get_user_by_username(runtime.session_factory, "admin")
        if user is None:  # pragma: no cover - 刚创建成功
            await runtime.close()
            return self._database_error(request, "管理员创建失败")
        self.runtime = runtime
        self.normal_app = create_app(cfg, runtime, auth_required=True, session_key=session_key)
        self.cleanup_task = asyncio.create_task(run_cleanup_loop(runtime))
        current = await settings_module.load(runtime.store)
        ttl_seconds = current.session_ttl_minutes * 60
        session = auth.create_session(user, session_key, ttl_seconds)
        if async_api.wants_json(request):
            response: Response = async_api.ok(
                request, message="安装完成", data={"redirect": "/"}
            )
            response.headers["Cache-Control"] = "no-store"
        else:
            response = self._render(
                "setup_complete.html",
                request,
                mcp_token=token,
                mcp_url=f"http://{cfg.host}:{cfg.port}/mcp",
            )
            response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            auth.SESSION_COOKIE,
            session,
            max_age=ttl_seconds,
            path="/",
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
        return response

    async def language(self, request: Request) -> Response:
        form = await request.form()
        if not self._csrf_ok(request, form):
            if async_api.wants_json(request):
                return JSONResponse({"error": "csrf_failed"}, status_code=403)
            return render.render(
                "error.html",
                request=request,
                title="请求已过期",
                message="页面已过期，请刷新后重试",
                code=403,
                status_code=403,
            )
        from dr_panda_mcp.web import i18n

        locale = i18n.normalize_locale(str(form.get("lang", "")))
        next_path = theme.safe_next(str(form.get("next", "/")), "/setup")
        response = RedirectResponse(next_path, status_code=303)
        return i18n.apply_language(response, locale)

    def _capture_database(self, form) -> None:
        self.state.db_type = str(form.get("db_type", self.state.db_type))
        self.state.sqlite_path = str(form.get("sqlite_path", self.state.sqlite_path)).strip()
        self.state.host = str(form.get("host", self.state.host)).strip()
        self.state.port = str(form.get("port", self.state.port)).strip()
        self.state.database = str(form.get("database", self.state.database)).strip()
        self.state.username = str(form.get("username", self.state.username)).strip()
        self.state.password = str(form.get("password", self.state.password))

    def _database_url(self) -> str:
        if self.state.db_type == "sqlite":
            if not self.state.sqlite_path:
                raise ValueError("SQLite 文件路径不能为空")
            return normalize_database_url(URL.create("sqlite", database=self.state.sqlite_path).render_as_string(hide_password=False))
        if self.state.db_type not in {"mysql", "postgresql"}:
            raise ValueError("不支持的配置库类型")
        if not self.state.host or not self.state.database or not self.state.username:
            raise ValueError("主机、数据库名和用户名不能为空")
        try:
            port = int(self.state.port)
        except ValueError as exc:
            raise ValueError("端口必须是整数") from exc
        base = "mysql" if self.state.db_type == "mysql" else "postgresql"
        query = {"charset": "utf8mb4"} if base == "mysql" else None
        return normalize_database_url(
            URL.create(
                base,
                username=self.state.username,
                password=self.state.password or None,
                host=self.state.host,
                port=port,
                database=self.state.database,
                query=query or {},
            ).render_as_string(hide_password=False)
        )

    def _csrf_ok(self, request: Request, form) -> bool:
        import hmac

        cookie = request.cookies.get(auth.CSRF_COOKIE, "")
        token = str(form.get("_csrf", ""))
        return bool(cookie and token and hmac.compare_digest(cookie, token))

    def _render(self, template: str, request: Request, *, status: int = 200, **context: Any) -> HTMLResponse:
        return render.render(template, request=request, status_code=status, **context)

    def _render_database(self, request: Request, *, error: str | None = None, status: int = 200) -> HTMLResponse:
        return self._render(
            "setup_database.html",
            request,
            state=self.state,
            error=error,
            status=status,
        )


async def _test_database(url: str) -> None:
    ensure_driver(url)
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


def _friendly_test_error(exc: Exception) -> str:
    if isinstance(exc, DrPandaError):
        return str(exc)
    if isinstance(exc, ValueError):
        return str(exc)
    return f"连接失败：{type(exc).__name__}"
