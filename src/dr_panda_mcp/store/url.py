"""配置库 URL 解析、异步驱动校验与引擎创建（planning 5.1 / 5.6）。

- ``normalize_database_url``：给 ``sqlite`` / ``mysql`` / ``postgresql`` 补异步驱动名
- ``ensure_driver``：驱动未安装时给出 extras 安装指引
- ``create_engine``：创建异步引擎；SQLite 打开 WAL、外键约束与 busy_timeout
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from dr_panda_mcp.errors import ConfigError, sync_extra_command

# 协议 -> (异步驱动, 可选依赖名)
DATABASE_DRIVERS: dict[str, tuple[str, str | None]] = {
    "sqlite": ("aiosqlite", None),
    "mysql": ("asyncmy", "mysql"),
    "postgresql": ("asyncpg", "postgres"),
}

# 便于测试替换
_find_spec = importlib.util.find_spec


def normalize_database_url(raw: str) -> str:
    """把 ``mysql://`` / ``postgresql://`` / ``sqlite://`` 补成异步驱动形式。"""
    value = (raw or "").strip()
    if not value:
        raise ConfigError("DR_PANDA_DATABASE_URL 不能为空")

    scheme = urlsplit(value).scheme
    base = scheme.split("+", 1)[0]
    if base not in DATABASE_DRIVERS:
        raise ConfigError(
            f"不支持的配置库类型：{scheme or '(空)'}；只支持 sqlite、mysql、postgresql"
        )
    if "+" in scheme:
        return value

    driver, _ = DATABASE_DRIVERS[base]
    return value.replace(f"{base}://", f"{base}+{driver}://", 1)


def ensure_driver(url: str) -> None:
    """确认 URL 对应的异步驱动已安装，否则给出安装指引。"""
    scheme = urlsplit(url).scheme
    base = scheme.split("+", 1)[0]
    driver = scheme.split("+", 1)[1] if "+" in scheme else DATABASE_DRIVERS[base][0]
    extra = DATABASE_DRIVERS[base][1]

    try:
        found = _find_spec(driver) is not None
    except (ImportError, ModuleNotFoundError):
        found = False

    if found:
        return

    if extra:
        hint = (
            f"{sync_extra_command(extra)}"
            f'（或 pip install "dr-panda-mcp[{extra}]"）。'
            "不要省略 --inexact，否则会卸掉其他已安装的 extra"
        )
        raise ConfigError(f"{base} 配置库需要 {driver}，当前环境没有安装；请执行：{hint}")
    raise ConfigError(f"sqlite 配置库需要 {driver}，当前环境没有安装；请执行：uv sync")


def database_path(url: str) -> Path | None:
    """返回 SQLite 数据库文件路径；内存库或非 SQLite 返回 ``None``。"""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return None
    database = parsed.database
    if not database or database == ":memory:":
        return None
    return Path(database)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """创建异步引擎；SQLite 额外设置连接级 PRAGMA。"""
    ensure_driver(url)
    path = database_path(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
    if path is not None:
        kwargs["connect_args"] = {"timeout": 5}

    engine = create_async_engine(url, **kwargs)
    if path is not None:
        event.listen(engine.sync_engine, "connect", _sqlite_on_connect)
    return engine


async def checkpoint_sqlite(engine: AsyncEngine) -> bool:
    """把 SQLite WAL 合并回主文件；非 SQLite/内存库直接跳过。

    只用于启动完成与正常关闭这两个安静时点；失败只记录日志，不阻断启动/关闭。
    """
    path = database_path(str(engine.url))
    if path is None:
        return False
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        return True
    except Exception:  # pragma: no cover - 取决于 SQLite 文件状态
        # 这里不能用 logger 引入循环依赖吗？url.py 只依赖 errors/config；用标准 logging。
        import logging

        logging.getLogger(__name__).warning("SQLite WAL checkpoint 失败", exc_info=True)
        return False


def _sqlite_on_connect(dbapi_connection, _connection_record) -> None:
    """每条 SQLite 连接都打开 WAL、外键与 busy_timeout。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()
