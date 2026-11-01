"""运行时装配：引擎、迁移、密钥与 ConfigStore（planning 3.2 启动序列）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dr_panda_mcp.catalog import Catalog
from dr_panda_mcp.config import Config
from dr_panda_mcp.crypto import DEFAULT_KEY_FILE, SecretBox, load_or_create_secret_box
from dr_panda_mcp.errors import StartupError
from dr_panda_mcp.store.migrate import migrate
from dr_panda_mcp.store.models import TargetRow
from dr_panda_mcp.store.repository import SqlConfigStore
from dr_panda_mcp.store.url import create_engine

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """进程级依赖：配置库引擎、仓储与密钥。"""

    config: Config
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    store: SqlConfigStore
    secret_box: SecretBox
    catalog: Catalog

    async def close(self) -> None:
        await self.catalog.close()
        await self.engine.dispose()


async def create_runtime(
    config: Config, *, key_file: Path = DEFAULT_KEY_FILE
) -> Runtime:
    """建引擎 → 迁移 → 加载密钥 → 校验已有密文 → 建仓储。"""
    engine = create_engine(config.database_url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        await migrate(engine)
        has_ciphertext = await _has_ciphertext(session_factory)
        secret_box = load_or_create_secret_box(
            config.secret_key_b64, key_file, has_ciphertext=has_ciphertext
        )
        store = SqlConfigStore(session_factory, secret_box)
        if has_ciphertext:
            await _assert_secrets_decryptable(store)
        return Runtime(
            config=config,
            engine=engine,
            session_factory=session_factory,
            store=store,
            secret_box=secret_box,
            catalog=Catalog(store),
        )
    except BaseException:
        await engine.dispose()
        raise


async def _has_ciphertext(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    async with session_factory() as session:
        result = await session.execute(select(TargetRow.secret_json))
        return any(bool(value) for (value,) in result.all())


async def _assert_secrets_decryptable(store: SqlConfigStore) -> None:
    broken = [
        target.name
        for target in await store.list_all()
        if target.secret_fields and not target.secret_ok
    ]
    if broken:
        raise StartupError(
            "配置库中以下目标的密钥无法解密："
            + "、".join(broken)
            + "；请恢复 data/secret.key 或 DR_PANDA_SECRET_KEY 备份后再启动"
        )
