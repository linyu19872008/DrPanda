"""Alembic 环境：由 :mod:`dr_panda_mcp.store.migrate` 传入同步连接后执行。"""

from __future__ import annotations

from alembic import context

from dr_panda_mcp.store.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError(
            "迁移必须通过 dr_panda_mcp.store.migrate 执行（需要传入连接）"
        )
    _run(connection)


run_migrations_online()
