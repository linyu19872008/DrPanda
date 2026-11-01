from __future__ import annotations

from dr_panda_mcp.masking import redact


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
