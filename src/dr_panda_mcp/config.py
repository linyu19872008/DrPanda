"""环境变量读取与校验（planning 3.2 / 3.3）。

配置库 URL 的规范化、驱动校验与引擎创建在 :mod:`dr_panda_mcp.store.url`。
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dr_panda_mcp.errors import ConfigError
from dr_panda_mcp.store.url import ensure_driver, normalize_database_url

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8111
DEFAULT_DATABASE_URL = "sqlite:///data/dr-panda.sqlite"
DEFAULT_LOG_LEVEL = "INFO"

# 数据目录：配置库、备份与加密密钥都放在这里（不进 git）
DEFAULT_DATA_DIR = "data"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class Config:
    """启动配置。``database_url`` 已补上异步驱动。"""

    host: str
    port: int
    database_url: str
    secret_key_b64: str | None
    log_level: str
    install_file: Path = Path("data/install.json")
    install_key_file: Path = Path("data/install.key")
    session_key_file: Path = Path("data/session.key")
    allow_remote: bool = False
    public_url: str | None = None


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """读取并校验环境变量；任何不合法的值都抛 ``ConfigError``。"""
    env = dict(os.environ if environ is None else environ)

    host = env.get("DR_PANDA_HOST", DEFAULT_HOST).strip()
    if not host:
        raise ConfigError("DR_PANDA_HOST 不能为空")

    port = _parse_port(env.get("DR_PANDA_PORT", str(DEFAULT_PORT)))

    database_url = normalize_database_url(
        env.get("DR_PANDA_DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    ensure_driver(database_url)

    secret_key_b64 = _parse_secret_key(env.get("DR_PANDA_SECRET_KEY"))

    allow_remote = env.get("DR_PANDA_ALLOW_REMOTE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    public_url = env.get("DR_PANDA_PUBLIC_URL", "").strip() or None

    log_level = env.get("DR_PANDA_LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
    if log_level not in LOG_LEVELS:
        raise ConfigError(
            f"DR_PANDA_LOG_LEVEL 必须是 {sorted(LOG_LEVELS)} 之一，当前：{log_level or '(空)'}"
        )

    return Config(
        host=host,
        port=port,
        database_url=database_url,
        secret_key_b64=secret_key_b64,
        log_level=log_level,
        allow_remote=allow_remote,
        public_url=public_url,
    )


def is_loopback_host(host: str) -> bool:
    """M7 之前只允许本机监听；避免无认证服务被误暴露到内网。"""
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def _parse_port(raw: str) -> int:
    try:
        port = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"DR_PANDA_PORT 必须是整数，当前：{raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"DR_PANDA_PORT 必须在 1–65535 之间，当前：{port}")
    return port


def _parse_secret_key(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError("DR_PANDA_SECRET_KEY 必须是 base64 编码的字符串") from exc
    if len(decoded) != 32:
        raise ConfigError(
            f"DR_PANDA_SECRET_KEY 解码后必须是 32 字节，当前 {len(decoded)} 字节"
        )
    return value
