"""ConfigStore 的 SQLAlchemy 异步实现（planning 5.2 / 5.4 / 5.8）。

- 唯一写 SQL 的地方；密钥加密/解密也只在这里调用 :class:`SecretBox`
- 写方法与审计在同一事务提交，失败一起回滚
- 读取时容忍单个目标的密钥解密失败：``secret_ok=False``，由上层决定报错
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dr_panda_mcp.crypto import SecretBox
from dr_panda_mcp.errors import (
    InvalidTarget,
    SecretUnavailable,
    StorageUnavailable,
    TargetNameTaken,
    TargetNotFound,
)
from dr_panda_mcp.store.models import AuditRow, SettingRow, TargetRow
from dr_panda_mcp.store.protocol import (
    TARGET_TYPES,
    AuditEntry,
    SecretPatch,
    Target,
    TargetDraft,
)

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def utc_now() -> datetime:
    return datetime.now(UTC)


class SqlConfigStore:
    """``ConfigStore`` 的 SQLite / MySQL / PostgreSQL 共用实现。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        secret_box: SecretBox,
    ) -> None:
        self._session_factory = session_factory
        self._box = secret_box

    async def ping(self) -> None:
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def list_all(self) -> list[Target]:
        return await self._select_targets()

    async def list_by_type(self, type: str) -> list[Target]:
        return await self._select_targets(type=type)

    async def get(self, name: str) -> Target | None:
        row = await self._one_target(select(TargetRow).where(TargetRow.name == name))
        return None if row is None else self._to_target(row)

    async def get_by_id(self, target_id: int) -> Target | None:
        row = await self._one_target(select(TargetRow).where(TargetRow.id == target_id))
        return None if row is None else self._to_target(row)

    async def create(self, draft: TargetDraft, actor: str) -> Target:
        draft = _validated(draft)
        now = utc_now()
        row = TargetRow(
            type=draft.type,
            name=draft.name,
            enabled=draft.enabled,
            options_json=dict(draft.options),
            secret_json=self._box.encrypt(draft.name, draft.secret_patch.set),
            created_at=now,
            updated_at=now,
            last_test_at=None,
            last_test_ok=None,
            last_test_error=None,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    session.add(row)
                    session.add(
                        self._audit_row(
                            actor, "target.create", draft.name, f"type={draft.type}"
                        )
                    )
                return self._to_target(row)
        except IntegrityError as exc:
            raise TargetNameTaken(f"目标名 {draft.name} 已存在") from exc
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc

    async def update(self, target_id: int, draft: TargetDraft, actor: str) -> Target:
        draft = _validated(draft)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    row = await self._require_row(session, target_id)
                    if draft.name != row.name or draft.type != row.type:
                        raise InvalidTarget("target 的名称与类型创建后不可修改")
                    envelope = dict(row.secret_json or {})
                    for field in draft.secret_patch.clear:
                        envelope.pop(field, None)
                    envelope.update(
                        self._box.encrypt(row.name, draft.secret_patch.set)
                    )
                    row.options_json = dict(draft.options)
                    row.secret_json = envelope
                    row.updated_at = utc_now()
                    session.add(self._audit_row(actor, "target.update", row.name, "options/secret"))
                return self._to_target(row)
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc

    async def set_enabled(self, target_id: int, enabled: bool, actor: str) -> Target:
        action = "target.enable" if enabled else "target.disable"
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    row = await self._require_row(session, target_id)
                    row.enabled = bool(enabled)
                    row.updated_at = utc_now()
                    session.add(
                        self._audit_row(actor, action, row.name, f"enabled={bool(enabled)}")
                    )
                return self._to_target(row)
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc

    async def delete(self, target_id: int, actor: str) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                row = await self._require_row(session, target_id)
                name = row.name
                await session.delete(row)
                session.add(self._audit_row(actor, "target.delete", name, "deleted"))
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc

    async def record_test(
        self, target_id: int, ok: bool, error: str | None, actor: str
    ) -> Target:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    row = await self._require_row(session, target_id)
                    row.last_test_at = utc_now()
                    row.last_test_ok = bool(ok)
                    row.last_test_error = _truncate(error, 512)
                    row.updated_at = utc_now()
                    summary = "ok" if ok else f"failed: {_truncate(error or '', 200)}"
                    session.add(self._audit_row(actor, "target.test", row.name, summary))
                return self._to_target(row)
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc

    async def append_audit(self, entry: AuditEntry) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                session.add(
                    AuditRow(
                        created_at=utc_now(),
                        actor=entry.actor,
                        action=entry.action,
                        target_name=entry.target_name,
                        summary=_truncate(entry.summary, 1024),
                    )
                )
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc

    async def get_settings(self) -> dict[str, str]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(SettingRow.key, SettingRow.value))).all()
        return {key: value for key, value in rows}

    async def update_settings(
        self, patch: Mapping[str, str], actor: str
    ) -> dict[str, str]:
        if not patch:
            return await self.get_settings()
        now = utc_now()
        try:
            async with self._session_factory() as session, session.begin():
                result = await session.execute(
                    select(SettingRow).where(SettingRow.key.in_(list(patch)))
                )
                existing = {row.key: row for row in result.scalars()}
                changes: list[str] = []
                for key, value in patch.items():
                    row = existing.get(key)
                    old = row.value if row is not None else None
                    if row is None:
                        session.add(SettingRow(key=key, value=value, updated_at=now))
                    else:
                        row.value = value
                        row.updated_at = now
                    changes.append(f"{key}: {old} -> {value}")
                session.add(
                    self._audit_row(
                        actor, "settings.update", None, "; ".join(changes)
                    )
                )
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"配置库写入失败：{exc}") from exc
        return await self.get_settings()

    async def _select_targets(self, *, type: str | None = None) -> list[Target]:
        query = select(TargetRow).order_by(TargetRow.type, TargetRow.name)
        if type is not None:
            query = query.where(TargetRow.type == type)
        async with self._session_factory() as session:
            rows = (await session.execute(query)).scalars().all()
        return [self._to_target(row) for row in rows]

    async def _one_target(self, query) -> TargetRow | None:
        async with self._session_factory() as session:
            return (await session.execute(query)).scalar_one_or_none()

    async def _require_row(self, session: AsyncSession, target_id: int) -> TargetRow:
        row = await session.get(TargetRow, target_id)
        if row is None:
            raise TargetNotFound(f"目标 id={target_id} 不存在")
        return row

    def _audit_row(
        self,
        actor: str,
        action: str,
        target_name: str | None,
        summary: str | None,
    ) -> AuditRow:
        return AuditRow(
            created_at=utc_now(),
            actor=actor,
            action=action,
            target_name=target_name,
            summary=_truncate(summary, 1024),
        )

    def _to_target(self, row: TargetRow) -> Target:
        envelopes: dict[str, Any] = row.secret_json or {}
        secret: dict[str, str] = {}
        secret_ok = True
        for field, envelope in envelopes.items():
            try:
                secret[field] = self._box.decrypt_field(row.name, field, envelope)
            except SecretUnavailable as exc:
                logger.warning("目标 %s 的密钥无法解密：%s", row.name, exc)
                secret_ok = False
        if not secret_ok:
            secret = {}
        return Target(
            id=row.id,
            type=row.type,
            name=row.name,
            enabled=row.enabled,
            options=dict(row.options_json or {}),
            secret=secret,
            secret_fields=frozenset(envelopes),
            secret_ok=secret_ok,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_test_at=row.last_test_at,
            last_test_ok=row.last_test_ok,
            last_test_error=row.last_test_error,
        )


def _validated(draft: TargetDraft) -> TargetDraft:
    name = (draft.name or "").strip()
    if not _NAME_RE.match(name):
        raise InvalidTarget(
            "名称只允许小写字母、数字与连字符，以字母或数字开头结尾，最长 64"
        )
    if draft.type not in TARGET_TYPES:
        raise InvalidTarget(f"未知的目标类型：{draft.type}")
    if not isinstance(draft.options, dict):
        raise InvalidTarget("options 必须是对象")
    if not isinstance(draft.secret_patch, SecretPatch):
        raise InvalidTarget("secret_patch 必须是 SecretPatch")
    for field, value in draft.secret_patch.set.items():
        if not field or not isinstance(value, str):
            raise InvalidTarget("密钥字段名不能为空，值必须是字符串")
    for field in draft.secret_patch.clear:
        if not field:
            raise InvalidTarget("要清除的密钥字段名不能为空")
    return TargetDraft(
        name=name,
        type=draft.type,
        enabled=bool(draft.enabled),
        options=dict(draft.options),
        secret_patch=draft.secret_patch,
    )


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[: limit - 1] + "…"
