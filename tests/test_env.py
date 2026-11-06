from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from dr_panda_mcp import cli
from dr_panda_mcp.env import EnvFileError, load_env_file


@pytest.fixture
def isolated_environ(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env = dict(os.environ)
    monkeypatch.setattr(os, "environ", env)
    return env


@pytest.fixture
def env_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_env(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def test_missing_env_file_uses_defaults(
    env_dir: Path, isolated_environ: dict[str, str]
) -> None:
    assert load_env_file() is None
    assert "DRPANDA_TEST_VALUE" not in isolated_environ


def test_env_file_is_loaded_and_real_env_wins(
    env_dir: Path, isolated_environ: dict[str, str]
) -> None:
    _write_env(
        env_dir / ".env",
        'export DRPANDA_TEST_A="a b"\n'
        "DRPANDA_TEST_B=\n"
        "DRPANDA_TEST_C=from-file\n"
        "# comment\n",
    )
    isolated_environ["DRPANDA_TEST_C"] = "from-env"

    loaded = load_env_file()

    assert loaded == env_dir / ".env"
    assert isolated_environ["DRPANDA_TEST_A"] == "a b"
    assert isolated_environ["DRPANDA_TEST_B"] == ""
    assert isolated_environ["DRPANDA_TEST_C"] == "from-env"


def test_malformed_env_file_fails(
    env_dir: Path, isolated_environ: dict[str, str]
) -> None:
    _write_env(env_dir / ".env", "NOT A KEY VALUE LINE\n")

    with pytest.raises(EnvFileError, match="not a valid KEY=VALUE"):
        load_env_file()


def test_env_directory_fails(
    env_dir: Path, isolated_environ: dict[str, str]
) -> None:
    (env_dir / ".env").mkdir()

    with pytest.raises(EnvFileError, match="not a regular file"):
        load_env_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX 权限位测试")
def test_env_file_with_loose_permissions_fails(
    env_dir: Path, isolated_environ: dict[str, str]
) -> None:
    path = env_dir / ".env"
    path.write_text("DRPANDA_TEST_A=1\n", encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(EnvFileError, match="permissions are too open"):
        load_env_file()

    assert path.stat().st_mode & stat.S_IMODE(0o777) == 0o644


def test_cli_loads_env_before_serving(
    env_dir: Path, isolated_environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(env_dir / ".env", "DRPANDA_TEST_A=loaded\n")
    calls: list[str] = []

    monkeypatch.setattr(cli, "serve_main", lambda: calls.append("serve") or 7)
    assert cli.main() == 7
    assert calls == ["serve"]
    assert isolated_environ["DRPANDA_TEST_A"] == "loaded"


def test_cli_fails_when_env_file_is_bad(
    env_dir: Path, isolated_environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(env_dir / ".env", "BAD LINE\n")
    calls: list[str] = []

    monkeypatch.setattr(cli, "serve_main", lambda: calls.append("serve") or 0)
    assert cli.main() == 2
    assert calls == []
