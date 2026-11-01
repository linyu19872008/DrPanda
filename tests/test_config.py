from __future__ import annotations

import base64

import pytest

from dr_panda_mcp.config import load_config
from dr_panda_mcp.errors import ConfigError
from dr_panda_mcp.store import url as url_module


def _env(**overrides: str) -> dict[str, str]:
    base = {"DR_PANDA_HOST": "127.0.0.1", "DR_PANDA_PORT": "8111"}
    base.update(overrides)
    return base


def test_defaults() -> None:
    cfg = load_config({})
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8111
    assert cfg.database_url.startswith("sqlite+aiosqlite://")
    assert cfg.secret_key_b64 is None
    assert cfg.log_level == "INFO"


def test_host_and_port_override() -> None:
    cfg = load_config(_env(DR_PANDA_HOST="0.0.0.0", DR_PANDA_PORT="9000"))
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9000


def test_empty_host_rejected() -> None:
    with pytest.raises(ConfigError, match="DR_PANDA_HOST"):
        load_config(_env(DR_PANDA_HOST="   "))


@pytest.mark.parametrize("raw", ["abc", "0", "65536", "-1", ""])
def test_invalid_port_rejected(raw: str) -> None:
    with pytest.raises(ConfigError, match="DR_PANDA_PORT"):
        load_config(_env(DR_PANDA_PORT=raw))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sqlite:///data/dr-panda.sqlite", "sqlite+aiosqlite:///data/dr-panda.sqlite"),
        ("mysql://u:p@h:3306/db", "mysql+asyncmy://u:p@h:3306/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("sqlite+aiosqlite:///tmp/x.sqlite", "sqlite+aiosqlite:///tmp/x.sqlite"),
    ],
)
def test_database_url_driver_completion(raw: str, expected: str) -> None:
    assert url_module.normalize_database_url(raw) == expected


def test_unsupported_database_url_rejected() -> None:
    with pytest.raises(ConfigError, match="不支持"):
        load_config(_env(DR_PANDA_DATABASE_URL="redis://localhost:6379/0"))


def test_missing_driver_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_module, "_find_spec", lambda name: None)
    with pytest.raises(ConfigError) as excinfo:
        load_config(_env(DR_PANDA_DATABASE_URL="mysql://u:p@localhost/db"))
    message = str(excinfo.value)
    assert "asyncmy" in message
    assert "mysql" in message


def test_sqlite_driver_installed() -> None:
    # 默认依赖里带 aiosqlite，保证开箱可用。
    load_config(_env())


def test_log_level_normalized() -> None:
    cfg = load_config(_env(DR_PANDA_LOG_LEVEL="debug"))
    assert cfg.log_level == "DEBUG"


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ConfigError, match="DR_PANDA_LOG_LEVEL"):
        load_config(_env(DR_PANDA_LOG_LEVEL="TRACE"))


def test_secret_key_valid(secret_key_b64: str) -> None:
    cfg = load_config(_env(DR_PANDA_SECRET_KEY=secret_key_b64))
    assert cfg.secret_key_b64 == secret_key_b64


@pytest.mark.parametrize(
    "raw",
    ["not-base64!!", base64.b64encode(b"too-short").decode()],
)
def test_secret_key_invalid(raw: str) -> None:
    with pytest.raises(ConfigError, match="DR_PANDA_SECRET_KEY"):
        load_config(_env(DR_PANDA_SECRET_KEY=raw))


def test_blank_secret_key_treated_as_unset() -> None:
    cfg = load_config(_env(DR_PANDA_SECRET_KEY="   "))
    assert cfg.secret_key_b64 is None


def test_sqlite_database_path() -> None:
    assert url_module.database_path("sqlite+aiosqlite:///data/dr-panda.sqlite") is not None
    assert url_module.database_path("sqlite+aiosqlite:///:memory:") is None
    assert url_module.database_path("postgresql+asyncpg://u:p@h/db") is None


def test_is_loopback_host() -> None:
    from dr_panda_mcp.config import is_loopback_host

    assert is_loopback_host("127.0.0.1") is True
    assert is_loopback_host("::1") is True
    assert is_loopback_host("localhost") is True
    assert is_loopback_host("0.0.0.0") is False
    assert is_loopback_host("10.0.0.1") is False
