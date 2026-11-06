from __future__ import annotations

from dr_panda_mcp import errors

EXPECTED_CODES = {
    "TARGET_NOT_FOUND",
    "TARGET_DISABLED",
    "TARGET_TYPE_MISMATCH",
    "NO_ENABLED_TARGET",
    "INVALID_ARGUMENT",
    "GUARD_REJECTED",
    "DANGEROUS_OPERATION",
    "SCOPE_DENIED",
    "UPSTREAM_NOT_FOUND",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_QUERY_ERROR",
    "UPSTREAM_AUTH",
    "STORAGE_UNAVAILABLE",
    "SECRET_UNAVAILABLE",
    "INTERNAL",
}


def test_error_codes_complete() -> None:
    assert EXPECTED_CODES <= errors.ALL_CODES


def test_dr_panda_error_carries_code() -> None:
    exc = errors.DrPandaError("boom", code=errors.INTERNAL)
    assert exc.code == errors.INTERNAL
    assert str(exc) == "boom"
