"""SQLAlchemy 2 声明式表（planning 5.3）。

四张表：``targets``、``audit``、``settings``、``settings_history``。所有时间列用 UTC 带时区语义：
SQLite 存不带偏移的文本，读出时由 :class:`UTCDateTime` 统一补成 UTC。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _pk_type():
    """主键类型：多数库用 BIGINT，SQLite 退化为 INTEGER 才能自增。"""
    return BigInteger().with_variant(Integer, "sqlite")


class UTCDateTime(TypeDecorator):
    """统一按 UTC 读写的时间类型，兼容 SQLite 丢失时区的问题。"""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("时间必须带时区（UTC）")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class TargetRow(Base):
    __tablename__ = "targets"
    __table_args__ = (
        UniqueConstraint("name", name="uq_targets_name"),
        Index("ix_targets_type", "type"),
    )

    id: Mapped[int] = mapped_column(_pk_type(), primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    secret_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_test_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(String(512), nullable=True)


class AuditRow(Base):
    __tablename__ = "audit"
    __table_args__ = (Index("ix_audit_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(_pk_type(), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    group_key: Mapped[str] = mapped_column(String(64), nullable=False)
    group_title: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    default_value: Mapped[str] = mapped_column(String(64), nullable=False)
    min_value: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    max_value: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    effect: Mapped[str] = mapped_column(String(64), nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    requires_restart: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    sort_order: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_mcp_token_hash", "mcp_token_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(_pk_type(), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    is_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    auth_version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    mcp_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mcp_token_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mcp_token_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    mcp_token_last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class SettingsHistoryRow(Base):
    __tablename__ = "settings_history"
    __table_args__ = (
        Index("ix_settings_history_key", "key"),
        Index("ix_settings_history_changed_at", "changed_at"),
    )

    id: Mapped[int] = mapped_column(_pk_type(), primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_value: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
