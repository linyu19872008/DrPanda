"""在当前服务所在项目补装一个可选客户端。

只接受固定 extra 名。命令是 ``uv sync --extra <name> --inexact``，
不会卸掉已经装好的其他客户端。同一时间只跑一个安装。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL_EXTRAS = frozenset({"mysql", "mongo", "redis", "kafka", "cls"})
INSTALL_TIMEOUT_SECONDS = 120
_PROJECT_NAME = 'name = "dr-panda-mcp"'


class InstallError(Exception):
    """安装没有开始，或 uv 没有成功。``reason`` 给页面展示。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InstallBusy(Exception):
    """已有安装在进行。"""


class _Gate:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.running = False


_gate = _Gate()


def find_project_root(cwd: Path, package_file: Path) -> Path | None:
    """先看启动目录，再看包文件所在目录，找到带本项目名的 pyproject.toml。"""
    for start in (cwd, *package_file.resolve().parents):
        found = _match_root(start)
        if found is not None:
            return found
    return None


def project_root() -> Path | None:
    return find_project_root(Path.cwd(), Path(__file__))


def _match_root(start: Path) -> Path | None:
    current = start
    while True:
        pyproject = current / "pyproject.toml"
        if pyproject.is_file() and _is_this_project(pyproject):
            return current
        if current.parent == current:
            return None
        current = current.parent


def _is_this_project(pyproject: Path) -> bool:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    return _PROJECT_NAME in text


async def install_extra(extra: str) -> None:
    """补装 ``extra``。忙、找不到项目、没有 uv 或 uv 失败时抛异常。"""
    if extra not in INSTALL_EXTRAS:
        raise InstallError("不支持安装该客户端")
    async with _gate.lock:
        if _gate.running:
            raise InstallBusy()
        _gate.running = True
    try:
        await _sync(extra)
    finally:
        async with _gate.lock:
            _gate.running = False


async def _sync(extra: str) -> None:
    root = project_root()
    if root is None:
        raise InstallError("找不到本服务的项目目录，无法安装")
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError("当前环境没有 uv，无法安装")
    logger.info("安装客户端 extra=%s root=%s", extra, root)
    try:
        process = await asyncio.create_subprocess_exec(
            uv,
            "sync",
            "--extra",
            extra,
            "--inexact",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise InstallError(f"无法启动 uv：{exc.strerror or exc}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), INSTALL_TIMEOUT_SECONDS
        )
    except TimeoutError:
        _kill(process)
        raise InstallError("安装超时，请稍后重试或手动执行命令") from None
    if process.returncode != 0:
        detail = _tail(stderr) or _tail(stdout) or f"uv sync 退出码 {process.returncode}"
        logger.warning("安装客户端失败 extra=%s: %s", extra, detail)
        raise InstallError(detail)


def _kill(process: asyncio.subprocess.Process) -> None:
    if process.pid is None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _tail(data: bytes | None, limit: int = 300) -> str:
    lines = [
        line.strip()
        for line in (data or b"").decode("utf-8", "replace").splitlines()
        if line.strip()
    ]
    for line in reversed(lines):
        if line.lower().startswith("error:"):
            return line[:limit]
    text = " ".join(lines)
    if len(text) <= limit:
        return text
    return text[-limit:]
