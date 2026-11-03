"""密钥加载与 AES-256-GCM 加解密（planning 5.8）。

落盘形态（``secret_json``）：字段名 -> 密文信封::

    {"password": {"v": 1, "kid": "k1", "nonce": "<base64>", "ct": "<base64>"}}

- 每个字段独立随机 nonce
- 版本 1 的 AAD 绑定 ``target 名 + 字段名``（旧数据）
- 版本 2 的 AAD 绑定 ``环境 key + target 名 + 字段名``，同名目标不能跨环境挪用密文
- 密钥来源：``DR_PANDA_SECRET_KEY`` 优先；否则 ``data/secret.key``（0600）
- 缺密钥且库里已有密文时拒绝启动，避免静默换钥匙导致全部目标不可用
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dr_panda_mcp.errors import SecretUnavailable, StartupError

logger = logging.getLogger(__name__)

DEFAULT_KEY_FILE = Path("data/secret.key")
KEY_BYTES = 32
NONCE_BYTES = 12
ENVELOPE_VERSION = 1
ENVELOPE_VERSION_V2 = 2
KEY_ID = "k1"


@dataclass(frozen=True)
class SecretBox:
    """持有主密钥，按字段加解密。"""

    key: bytes
    kid: str = KEY_ID

    def encrypt(
        self,
        target_name: str,
        values: Mapping[str, str],
        *,
        environment: str | None = None,
    ) -> dict[str, dict]:
        return {
            field: self.encrypt_field(target_name, field, value, environment=environment)
            for field, value in values.items()
        }

    def encrypt_field(
        self,
        target_name: str,
        field: str,
        value: str,
        *,
        environment: str | None = None,
    ) -> dict:
        if not isinstance(value, str):
            raise SecretUnavailable(f"字段 {field} 的密钥必须是字符串")
        version = ENVELOPE_VERSION_V2 if environment else ENVELOPE_VERSION
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(self.key).encrypt(
            nonce, value.encode("utf-8"), _aad(target_name, field, environment)
        )
        return {
            "v": version,
            "kid": self.kid,
            "nonce": _b64(nonce),
            "ct": _b64(ciphertext),
        }

    def decrypt_field(
        self,
        target_name: str,
        field: str,
        envelope: Mapping[str, object],
        *,
        environment: str | None = None,
    ) -> str:
        version = envelope.get("v")
        if version == ENVELOPE_VERSION:
            aad = _aad(target_name, field, None)
        elif version == ENVELOPE_VERSION_V2:
            if not environment:
                raise SecretUnavailable(f"目标 {target_name} 的密钥版本不支持")
            aad = _aad(target_name, field, environment)
        else:
            raise SecretUnavailable(f"目标 {target_name} 的密钥版本不支持")
        if envelope.get("kid") != self.kid:
            raise SecretUnavailable(f"目标 {target_name} 的密钥版本与当前密钥不匹配")
        nonce = _unb64(str(envelope.get("nonce", "")), target_name)
        ciphertext = _unb64(str(envelope.get("ct", "")), target_name)
        try:
            plaintext = AESGCM(self.key).decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise SecretUnavailable(f"目标 {target_name} 的密钥无法解密") from exc
        return plaintext.decode("utf-8")


def _aad(target_name: str, field: str, environment: str | None = None) -> bytes:
    if environment:
        return f"drpanda:{environment}:{target_name}:{field}".encode()
    return f"drpanda:{target_name}:{field}".encode()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode()


def _unb64(value: str, target_name: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SecretUnavailable(f"目标 {target_name} 的密钥密文损坏") from exc


def decode_key(encoded: str) -> bytes:
    try:
        key = base64.b64decode(encoded.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StartupError("加密密钥必须是 base64 编码的字符串") from exc
    if len(key) != KEY_BYTES:
        raise StartupError(f"加密密钥解码后必须是 {KEY_BYTES} 字节，当前 {len(key)} 字节")
    return key


def load_or_create_secret_box(
    secret_key_b64: str | None,
    key_file: Path = DEFAULT_KEY_FILE,
    *,
    has_ciphertext: bool,
) -> SecretBox:
    """按 3.2 第 4 步加载密钥；必要时生成，必要时拒绝启动。"""
    if secret_key_b64:
        return SecretBox(decode_key(secret_key_b64))

    if key_file.exists():
        return SecretBox(decode_key(key_file.read_text(encoding="utf-8")))

    if has_ciphertext:
        raise StartupError(
            f"配置库里已有加密数据，但没有找到密钥文件 {key_file}，"
            "也没有设置 DR_PANDA_SECRET_KEY。请恢复密钥备份后再启动"
        )

    key = os.urandom(KEY_BYTES)
    _write_key_file(key_file, key)
    logger.warning("已生成新的加密密钥：%s（请与配置库一起备份）", key_file)
    return SecretBox(key)


def _write_key_file(key_file: Path, key: bytes) -> None:
    key_file.parent.mkdir(parents=True, exist_ok=True)
    temp = key_file.with_name(key_file.name + ".tmp")
    temp.write_text(_b64(key) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(key_file)
    os.chmod(key_file, 0o600)
