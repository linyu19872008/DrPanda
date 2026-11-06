from __future__ import annotations

import base64
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from dr_panda_mcp import _run, main
from dr_panda_mcp.config import Config
from dr_panda_mcp.errors import StartupError
from dr_panda_mcp.install import save_install_state
from dr_panda_mcp.runtime import create_runtime
from dr_panda_mcp.store.protocol import SecretPatch, TargetDraft


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server(env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dr_panda_mcp"],
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_main_exits_2_on_bad_config(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("DR_PANDA_PORT", "not-a-port")

    assert main() == 2
    stderr = capsys.readouterr().err
    assert "DR_PANDA_PORT" in stderr


async def test_non_loopback_requires_completed_install(tmp_path: Path) -> None:
    cfg = Config(
        host="0.0.0.0",
        port=0,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        secret_key_b64=None,
        log_level="INFO",
        install_file=tmp_path / "install.json",
        install_key_file=tmp_path / "install.key",
        session_key_file=tmp_path / "session.key",
    )

    with pytest.raises(StartupError, match="first installation"):
        await _run(cfg)


def test_main_exits_non_zero_when_port_taken() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    try:
        env = dict(os.environ)
        env["DR_PANDA_HOST"] = "127.0.0.1"
        env["DR_PANDA_PORT"] = str(port)
        env.pop("DR_PANDA_SECRET_KEY", None)
        result = _run_server(env, Path.cwd())
    finally:
        listener.close()

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "DR_PANDA_PORT" in output


async def _prepare_database(tmp_path: Path) -> tuple[Path, Path]:
    """建库并登记一个带密钥的目标，返回 (db 路径, 密钥文件路径)。"""
    db_path = tmp_path / "dr-panda.sqlite"
    key_file = tmp_path / "data" / "secret.key"
    config = Config(
        host="127.0.0.1",
        port=8111,
        database_url=f"sqlite+aiosqlite:///{db_path}",
        secret_key_b64=None,
        log_level="INFO",
    )
    runtime = await create_runtime(config, key_file=key_file)
    try:
        await runtime.store.create(
            TargetDraft(
                name="order-mysql",
                type="mysql",
                enabled=True,
                options={"host": "127.0.0.1"},
                secret_patch=SecretPatch(set={"password": "secret-value"}),
            ),
            "anonymous",
        )
    finally:
        await runtime.close()
    # M7 起进程启动先进入首次安装；这两个用例验证已安装后的密钥校验，
    # 因此写入临时 install 状态让 main 直接进入运行时。
    save_install_state(
        tmp_path / "data" / "install.json",
        tmp_path / "data" / "install.key",
        f"sqlite+aiosqlite:///{db_path}",
    )
    return db_path, key_file


def _base_env(tmp_path: Path, db_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["DR_PANDA_HOST"] = "127.0.0.1"
    env["DR_PANDA_PORT"] = str(_free_port())
    env["DR_PANDA_DATABASE_URL"] = f"sqlite:///{db_path}"
    env["DR_PANDA_LOG_LEVEL"] = "WARNING"
    env.pop("DR_PANDA_SECRET_KEY", None)
    env.pop("DR_PANDA_DATA_DIR", None)
    return env


async def test_startup_fails_when_key_does_not_match(tmp_path: Path) -> None:
    db_path, _key_file = await _prepare_database(tmp_path)
    env = _base_env(tmp_path, db_path)
    env["DR_PANDA_SECRET_KEY"] = base64.b64encode(b"\x01" * 32).decode()

    result = _run_server(env, tmp_path)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "密钥无法解密" in output
    assert "DR_PANDA_SECRET_KEY" in output


async def test_startup_fails_when_key_file_missing(tmp_path: Path) -> None:
    db_path, key_file = await _prepare_database(tmp_path)
    key_file.unlink()
    env = _base_env(tmp_path, db_path)

    result = _run_server(env, tmp_path)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "key file" in output
    assert "startup failed" in output
