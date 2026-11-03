from __future__ import annotations

from dr_panda_mcp.masking import redact
from dr_panda_mcp.tools.base import mask_params


def test_redact_secret_literal() -> None:
    assert redact("connection failed for pw-123", ["pw-123"]) == "connection failed for ***"


def test_redact_phone() -> None:
    assert "13800138000" not in redact("phone 13800138000")


def test_redact_id_card() -> None:
    result = redact("id 110101199001011234")

    assert "110101199001011234" not in result
    assert result.startswith("id 110101") and result.endswith("1234")


def test_redact_credential_words() -> None:
    result = redact("token=abc password: p@ss")

    assert "abc" not in result
    assert "p@ss" not in result
    assert "token=***" in result


def test_redact_empty() -> None:
    assert redact("") == ""


def test_redact_ignores_empty_secret() -> None:
    assert redact("hello", ["", None]) == "hello"  # type: ignore[list-item]


def test_mask_params_redacts_before_cutting() -> None:
    secret = "SECRETVALUE" * 6
    params = {"query": ("a" * 180) + secret}

    class _Target:
        def __init__(self) -> None:
            self.secret = {"password": secret}

    text = mask_params(params, _Target())  # type: ignore[arg-type]

    assert secret not in text
    assert len(text) <= 200
    assert "***" in text
