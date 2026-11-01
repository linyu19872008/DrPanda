from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from dr_panda_mcp.config import Config
from dr_panda_mcp.runtime import Runtime, create_runtime


@pytest.fixture
def secret_key_b64() -> str:
    """32 字节测试密钥的 base64 表示。"""
    return base64.b64encode(b"\x00" * 32).decode()


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """不依赖本机环境的启动配置。"""
    return Config(
        host="127.0.0.1",
        port=8111,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'dr-panda.sqlite'}",
        secret_key_b64=None,
        log_level="INFO",
    )


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[Runtime]:
    """临时目录里的完整运行时：迁移后的 SQLite + 临时密钥 + 仓储。"""
    cfg = Config(
        host="127.0.0.1",
        port=8111,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'dr-panda.sqlite'}",
        secret_key_b64=None,
        log_level="INFO",
    )
    rt = await create_runtime(cfg, key_file=tmp_path / "data" / "secret.key")
    try:
        yield rt
    finally:
        await rt.close()
