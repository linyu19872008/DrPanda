"""首次安装状态：本地 install.json 与配置库 URL 加密存储。

安装前配置库尚未确定，所以“是否已安装”不能只存在配置库。install.json 只保存
安装状态和加密后的数据库 URL，密码、MCP Token 不入该文件。
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dr_panda_mcp.errors import StartupError

INSTALL_VERSION = 1
INSTALL_KEY_BYTES = 32
NONCE_BYTES = 12


@dataclass(frozen=True)
class InstallState:
    database_url: str
    installed_at: str


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def load_or_create_install_key(path: Path) -> bytes:
    if path.exists():
        try:
            key = base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True)
        except (ValueError, OSError) as exc:
            raise StartupError(f"installation key file is corrupted: {path}") from exc
        if len(key) != INSTALL_KEY_BYTES:
            raise StartupError(f"installation key must be {INSTALL_KEY_BYTES} bytes: {path}")
        return key

    key = os.urandom(INSTALL_KEY_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(_b64(key) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    os.chmod(path, 0o600)
    return key


def load_install_state(install_file: Path, key_file: Path) -> InstallState | None:
    if not install_file.exists():
        return None
    key = load_or_create_install_key(key_file)
    try:
        raw = json.loads(install_file.read_text(encoding="utf-8"))
        if raw.get("v") != INSTALL_VERSION:
            raise StartupError("unsupported installation state version")
        envelope = raw["database_url"]
        nonce = _unb64(envelope["nonce"])
        ciphertext = _unb64(envelope["ct"])
        database_url = AESGCM(key).decrypt(
            nonce, ciphertext, b"drpanda:install:database_url"
        ).decode("utf-8")
        return InstallState(database_url=database_url, installed_at=str(raw.get("installed_at", "")))
    except (KeyError, TypeError, ValueError, InvalidTag) as exc:
        raise StartupError(f"installation state file is corrupted: {install_file}") from exc


def save_install_state(install_file: Path, key_file: Path, database_url: str) -> None:
    key = load_or_create_install_key(key_file)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(
        nonce, database_url.encode("utf-8"), b"drpanda:install:database_url"
    )
    payload = {
        "v": INSTALL_VERSION,
        "installed_at": datetime.now(UTC).isoformat(),
        "database_url": {"nonce": _b64(nonce), "ct": _b64(ciphertext)},
    }
    install_file.parent.mkdir(parents=True, exist_ok=True)
    temp = install_file.with_name(install_file.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(install_file)
    os.chmod(install_file, 0o600)
