"""ConfigStore 接口与数据对象（planning 5.2）。

网页、工具、连接器只依赖这里；不出现 SQLite / MySQL / PostgreSQL 的类型或 SQL。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

TARGET_TYPES = frozenset(
    {"mysql", "mongo", "elasticsearch", "redis", "gitlab", "rabbitmq", "kafka", "cls"}
)


@dataclass(frozen=True)
class Target:
    """配置库里的一个排查目标。``secret`` 是解密后的值，只在进程内使用。"""

    id: int
    type: str
    name: str
    enabled: bool
    options: dict[str, Any]
    secret: dict[str, str]
    secret_fields: frozenset[str]
    secret_ok: bool
    created_at: datetime
    updated_at: datetime
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_error: str | None


@dataclass(frozen=True)
class SecretPatch:
    """密钥补丁：``set`` 覆盖或新增，``clear`` 置空。"""

    set: dict[str, str] = field(default_factory=dict)
    clear: frozenset[str] = field(default_factory=frozenset)

    def is_empty(self) -> bool:
        return not self.set and not self.clear


@dataclass(frozen=True)
class TargetDraft:
    """新建与修改共用的入参。修改时 ``name`` 与 ``type`` 必须与库中一致。"""

    name: str
    type: str
    enabled: bool
    options: dict[str, Any]
    secret_patch: SecretPatch = field(default_factory=SecretPatch)


@dataclass(frozen=True)
class AuditEntry:
    actor: str
    action: str
    target_name: str | None = None
    summary: str | None = None


@dataclass(frozen=True)
class SettingsChange:
    """一次系统配置修改的审计摘要。"""

    created_at: datetime
    actor: str
    summary: str | None


@dataclass(frozen=True)
class Settings:
    """解析并校验后的运行时策略（planning 4.5）。"""

    audit_retention_days: int
    target_max_concurrency: int
    default_target_timeout_s: int = 15
    default_target_max_rows: int = 100
    default_target_max_bytes: int = 102_400
    audit_cleanup_interval_minutes: int = 60
    catalog_max_clients: int = 32


@runtime_checkable
class ConfigStore(Protocol):
    """配置库接口。所有写方法都在同一事务里追加审计。"""

    async def ping(self) -> None: ...
    async def list_all(self) -> list[Target]: ...
    async def list_by_type(self, type: str) -> list[Target]: ...
    async def get(self, name: str) -> Target | None: ...
    async def get_by_id(self, target_id: int) -> Target | None: ...

    async def create(self, draft: TargetDraft, actor: str) -> Target: ...
    async def update(self, target_id: int, draft: TargetDraft, actor: str) -> Target: ...
    async def set_enabled(self, target_id: int, enabled: bool, actor: str) -> Target: ...
    async def delete(self, target_id: int, actor: str) -> None: ...
    async def record_test(
        self, target_id: int, ok: bool, error: str | None, actor: str
    ) -> Target: ...
    async def append_audit(self, entry: AuditEntry) -> None: ...

    async def get_settings(self) -> dict[str, str]: ...
    async def update_settings(self, patch: Mapping[str, str], actor: str) -> dict[str, str]: ...
    async def list_settings_changes(
        self, limit: int = 5
    ) -> list[SettingsChange]: ...
