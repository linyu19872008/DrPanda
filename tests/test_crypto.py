from __future__ import annotations

import base64
from pathlib import Path

import pytest

from dr_panda_mcp.crypto import (
    KEY_BYTES,
    SecretBox,
    decode_key,
    load_or_create_secret_box,
)
from dr_panda_mcp.errors import SecretUnavailable, StartupError

KEY = b"\x02" * KEY_BYTES
OTHER_KEY = b"\x03" * KEY_BYTES


def _box() -> SecretBox:
    return SecretBox(KEY)


def test_encrypt_decrypt_roundtrip() -> None:
    box = _box()
    envelope = box.encrypt_field("order-mysql", "password", "p@ss-秘密")

    assert envelope["v"] == 1
    assert envelope["kid"] == "k1"
    assert set(envelope) == {"v", "kid", "nonce", "ct"}
    assert box.decrypt_field("order-mysql", "password", envelope) == "p@ss-秘密"


def test_nonce_is_unique_per_field() -> None:
    box = _box()
    first = box.encrypt_field("order-mysql", "password", "same")
    second = box.encrypt_field("order-mysql", "password", "same")

    assert first["nonce"] != second["nonce"]
    assert first["ct"] != second["ct"]


def test_aad_binds_target_and_field() -> None:
    box = _box()
    envelope = box.encrypt_field("order-mysql", "password", "p@ss")

    with pytest.raises(SecretUnavailable):
        box.decrypt_field("pay-mysql", "password", envelope)
    with pytest.raises(SecretUnavailable):
        box.decrypt_field("order-mysql", "token", envelope)


def test_wrong_key_cannot_decrypt() -> None:
    envelope = _box().encrypt_field("order-mysql", "password", "p@ss")

    with pytest.raises(SecretUnavailable):
        SecretBox(OTHER_KEY).decrypt_field("order-mysql", "password", envelope)


def test_tampered_ciphertext_rejected() -> None:
    box = _box()
    envelope = box.encrypt_field("order-mysql", "password", "p@ss")
    envelope["ct"] = base64.b64encode(b"tampered").decode()

    with pytest.raises(SecretUnavailable):
        box.decrypt_field("order-mysql", "password", envelope)


def test_corrupt_base64_rejected() -> None:
    box = _box()
    envelope = {"v": 1, "kid": "k1", "nonce": "!!", "ct": "!!"}

    with pytest.raises(SecretUnavailable):
        box.decrypt_field("order-mysql", "password", envelope)


def test_load_from_env_key(secret_key_b64: str, tmp_path: Path) -> None:
    key_file = tmp_path / "secret.key"
    box = load_or_create_secret_box(secret_key_b64, key_file, has_ciphertext=False)

    assert not key_file.exists()
    envelope = box.encrypt_field("order-mysql", "password", "p@ss")
    assert box.decrypt_field("order-mysql", "password", envelope) == "p@ss"


def test_generate_key_when_no_ciphertext(tmp_path: Path) -> None:
    key_file = tmp_path / "data" / "secret.key"
    box = load_or_create_secret_box(None, key_file, has_ciphertext=False)

    assert key_file.exists()
    assert (key_file.stat().st_mode & 0o777) == 0o600
    assert decode_key(key_file.read_text(encoding="utf-8")) == box.key


def test_existing_key_file_loaded(tmp_path: Path) -> None:
    key_file = tmp_path / "secret.key"
    key_file.write_text(base64.b64encode(KEY).decode(), encoding="utf-8")

    box = load_or_create_secret_box(None, key_file, has_ciphertext=False)

    assert box.key == KEY


def test_missing_key_with_ciphertext_refuses(tmp_path: Path) -> None:
    with pytest.raises(StartupError, match="密钥文件"):
        load_or_create_secret_box(None, tmp_path / "secret.key", has_ciphertext=True)


def test_invalid_key_file_refuses(tmp_path: Path) -> None:
    key_file = tmp_path / "secret.key"
    key_file.write_text("not-a-key", encoding="utf-8")

    with pytest.raises(StartupError, match="base64"):
        load_or_create_secret_box(None, key_file, has_ciphertext=False)


def test_decode_key_length_checked() -> None:
    with pytest.raises(StartupError, match="32 字节"):
        decode_key(base64.b64encode(b"short").decode())
