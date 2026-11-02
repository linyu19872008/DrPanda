"""M7 认证基础设施：密码哈希、用户、Session、MCP Token。

- 密码只存 scrypt 哈希；
- Web Session 使用 HMAC-SHA256 签名的 HttpOnly Cookie，无服务端 Session 表；
- MCP 使用独立 Bearer Token，服务端只存 SHA-256。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dr_panda_mcp.errors import StartupError
from dr_panda_mcp.store.models import UserRow

logger = logging.getLogger(__name__)

PASSWORD_MIN_LENGTH = 8
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SESSION_COOKIE = "drpanda_session"
CSRF_COOKIE = "drpanda_csrf"
SETUP_COOKIE = "drpanda_setup"
SESSION_KEY_BYTES = 32
SESSION_MAX_AGE_DEFAULT = 720 * 60

_current_actor: ContextVar[str] = ContextVar("drpanda_actor", default="anonymous")
_current_user: ContextVar[User | None] = ContextVar("drpanda_user", default=None)


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    is_enabled: bool
    auth_version: int


@dataclass(frozen=True)
class UserProfile:
    user: User
    last_login_at: datetime | None
    mcp_token_prefix: str | None
    mcp_token_created_at: datetime | None
    mcp_token_last_used_at: datetime | None
    has_mcp_token: bool


def current_actor() -> str:
    user = _current_user.get()
    return user.username if user is not None else _current_actor.get()


def current_user() -> User | None:
    return _current_user.get()


@contextmanager
def use_actor(actor: str, user: User | None = None) -> Iterator[None]:
    actor_token = _current_actor.set(actor or "anonymous")
    user_token = _current_user.set(user)
    try:
        yield
    finally:
        _current_actor.reset(actor_token)
        _current_user.reset(user_token)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def password_problem(password: str) -> str | None:
    """返回密码策略错误；通过返回 None。"""
    if len(password) < PASSWORD_MIN_LENGTH:
        return "密码至少需要 8 位"
    if len(password) > 256:
        return "密码不能超过 256 位"
    return None


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


async def verify_password_async(password: str, encoded: str) -> bool:
    return await asyncio.to_thread(verify_password, password, encoded)


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(digest, _unb64(digest_b64))
    except (ValueError, TypeError, binascii.Error):
        return False


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def load_or_create_session_key(path: Path) -> bytes:
    if path.exists():
        try:
            key = base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise StartupError(f"Session 密钥文件损坏：{path}") from exc
        if len(key) != SESSION_KEY_BYTES:
            raise StartupError(f"Session 密钥必须是 {SESSION_KEY_BYTES} 字节：{path}")
        return key

    key = os.urandom(SESSION_KEY_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(_b64(key) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    os.chmod(path, 0o600)
    logger.warning("已生成新的 Session 密钥：%s（请与配置库一起备份）", path)
    return key


def _session_signature(payload: str, key: bytes) -> str:
    return base64.urlsafe_b64encode(
        hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")


def create_session(user: User, key: bytes, ttl_seconds: int) -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "uid": user.id,
        "username": user.username,
        "role": user.role,
        "av": user.auth_version,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{encoded}.{_session_signature(encoded, key)}"


def verify_session(value: str, key: bytes) -> dict[str, Any] | None:
    try:
        encoded, signature = value.split(".", 1)
        expected = _session_signature(encoded, key)
        if not hmac.compare_digest(signature, expected):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error):
        return None


def user_from_row(row: UserRow) -> User:
    return User(
        id=row.id,
        username=row.username,
        role=row.role,
        is_enabled=bool(row.is_enabled),
        auth_version=row.auth_version,
    )


async def authenticate(
    session_factory: async_sessionmaker[AsyncSession], username: str, password: str
) -> User | None:
    async with session_factory() as session:
        row = await session.scalar(select(UserRow).where(UserRow.username == username))
        if row is None:
            return None
    if not await asyncio.to_thread(verify_password, password, row.password_hash):
        return None
    user = user_from_row(row)
    if not user.is_enabled or user.role != "admin":
        return None
    return user


async def get_user_by_username(
    session_factory: async_sessionmaker[AsyncSession], username: str
) -> User | None:
    async with session_factory() as session:
        row = await session.scalar(select(UserRow).where(UserRow.username == username))
        return user_from_row(row) if row is not None else None


async def get_user_by_id(
    session_factory: async_sessionmaker[AsyncSession], user_id: int
) -> User | None:
    async with session_factory() as session:
        row = await session.get(UserRow, user_id)
        return user_from_row(row) if row is not None else None


async def get_user_by_token_hash(
    session_factory: async_sessionmaker[AsyncSession], token_hash: str
) -> User | None:
    async with session_factory() as session:
        row = await session.scalar(
            select(UserRow).where(UserRow.mcp_token_hash == token_hash)
        )
        return user_from_row(row) if row is not None else None


async def create_admin(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    password_hash: str,
    mcp_token_hash: str | None = None,
    mcp_token_prefix: str | None = None,
) -> User:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        row = UserRow(
            username="admin",
            password_hash=password_hash,
            role="admin",
            is_enabled=True,
            auth_version=1,
            mcp_token_hash=mcp_token_hash,
            mcp_token_prefix=mcp_token_prefix,
            mcp_token_created_at=now if mcp_token_hash else None,
            mcp_token_last_used_at=None,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return user_from_row(row)


async def has_admin(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    async with session_factory() as session:
        return (
            await session.scalar(
                select(UserRow.id).where(
                    UserRow.role == "admin", UserRow.is_enabled.is_(True)
                )
            )
        ) is not None


async def get_profile(
    session_factory: async_sessionmaker[AsyncSession], user_id: int
) -> UserProfile | None:
    async with session_factory() as session:
        row = await session.get(UserRow, user_id)
        if row is None:
            return None
        return UserProfile(
            user=user_from_row(row),
            last_login_at=row.last_login_at,
            mcp_token_prefix=row.mcp_token_prefix,
            mcp_token_created_at=row.mcp_token_created_at,
            mcp_token_last_used_at=row.mcp_token_last_used_at,
            has_mcp_token=row.mcp_token_hash is not None,
        )


async def touch_mcp_token_used(
    session_factory: async_sessionmaker[AsyncSession], user_id: int
) -> None:
    """节流更新 Token 最近使用时间，避免每次 MCP 请求都写库。"""
    now = datetime.now(UTC)
    threshold = datetime.fromtimestamp(now.timestamp() - 60, tz=UTC)
    async with session_factory() as session, session.begin():
        await session.execute(
            update(UserRow)
            .where(
                UserRow.id == user_id,
                or_(
                    UserRow.mcp_token_last_used_at.is_(None),
                    UserRow.mcp_token_last_used_at < threshold,
                ),
            )
            .values(mcp_token_last_used_at=now)
        )


async def set_password(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    password_hash: str,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        row = await session.get(UserRow, user_id)
        if row is None:
            raise ValueError("user not found")
        row.password_hash = password_hash
        row.auth_version += 1
        row.updated_at = now


async def rotate_mcp_token(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    *,
    token_hash: str,
    token_prefix: str,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        row = await session.get(UserRow, user_id)
        if row is None:
            raise ValueError("user not found")
        row.mcp_token_hash = token_hash
        row.mcp_token_prefix = token_prefix
        row.mcp_token_created_at = now
        row.mcp_token_last_used_at = None
        row.updated_at = now


async def set_last_login(
    session_factory: async_sessionmaker[AsyncSession], user_id: int
) -> None:
    async with session_factory() as session, session.begin():
        row = await session.get(UserRow, user_id)
        if row is not None:
            row.last_login_at = datetime.now(UTC)
