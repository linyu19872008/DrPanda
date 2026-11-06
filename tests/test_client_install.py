from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dr_panda_mcp import client_install
from dr_panda_mcp.client_install import InstallBusy, InstallError


@pytest.fixture(autouse=True)
def _reset_install_gate() -> None:
    client_install._gate.running = False
    yield
    client_install._gate.running = False


def test_find_project_root_prefers_launch_directory(tmp_path: Path) -> None:
    root = tmp_path / "app"
    package = root / "src" / "pkg"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text('name = "dr-panda-mcp"\n', encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    (other / "pyproject.toml").write_text('name = "else"\n', encoding="utf-8")

    assert client_install.find_project_root(root / "sub", package / "mod.py") == root
    assert client_install.find_project_root(other, package / "mod.py") == root


async def test_sync_command_is_inexact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "app"
    root.mkdir()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class Process:
        returncode = 0
        pid = 42

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"installed", b""

        def kill(self) -> None:
            return None

    async def fake_exec(*args: object, **kwargs: object) -> Process:
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(client_install, "project_root", lambda: root)
    monkeypatch.setattr(client_install.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(client_install.asyncio, "create_subprocess_exec", fake_exec)

    await client_install.install_extra("mongo")

    args, kwargs = calls[0]
    assert args == ("/usr/bin/uv", "sync", "--extra", "mongo", "--inexact")
    assert kwargs["cwd"] == root
    assert kwargs["start_new_session"] is True


async def test_unknown_extra_is_rejected() -> None:
    with pytest.raises(InstallError):
        await client_install.install_extra("postgres")
    with pytest.raises(InstallError):
        await client_install.install_extra("mongo && rm -rf /")


async def test_second_install_is_rejected_while_one_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(_extra: str) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(client_install, "_sync", slow)
    running = asyncio.create_task(client_install.install_extra("mongo"))
    await started.wait()
    with pytest.raises(InstallBusy):
        await client_install.install_extra("redis")
    release.set()
    await running


async def test_uv_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = 1
        pid = 7

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"Using CPython 3.11\nResolved in 12ms\nerror: network down"

        def kill(self) -> None:
            return None

    async def fake_exec(*_args: object, **_kwargs: object) -> Process:
        return Process()

    monkeypatch.setattr(client_install, "project_root", lambda: Path("/tmp/app"))
    monkeypatch.setattr(client_install.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(client_install.asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(InstallError, match="network down"):
        await client_install.install_extra("cls")


async def test_timeout_kills_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    killed: list[int] = []

    class Process:
        returncode = None
        pid = 99

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(5)
            return b"", b""

        def kill(self) -> None:
            killed.append(self.pid)

    async def fake_exec(*_args: object, **_kwargs: object) -> Process:
        return Process()

    monkeypatch.setattr(client_install, "project_root", lambda: Path("/tmp/app"))
    monkeypatch.setattr(client_install.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(client_install.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client_install, "INSTALL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(client_install, "_kill", lambda process: killed.append(process.pid))

    with pytest.raises(InstallError, match="installation timed out"):
        await client_install.install_extra("redis")
    assert killed == [99]
