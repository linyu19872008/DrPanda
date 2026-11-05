from __future__ import annotations

from dr_panda_mcp.masking import redact
from dr_panda_mcp.tools.base import build_tool_summary, mask_params
from dr_panda_mcp.web.audit_page import describe_summary


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


def test_mask_params_redacts_the_whole_value() -> None:
    secret = "SECRETVALUE" * 6
    params = {"query": ("a" * 180) + secret}

    class _Target:
        def __init__(self) -> None:
            self.secret = {"password": secret}

    text = mask_params(params, _Target())  # type: ignore[arg-type]

    assert secret not in text
    assert "a" * 180 in text
    assert "***" in text


def test_ordinary_sql_is_stored_whole() -> None:
    sql = (
        "SELECT id, userid, giftid, oldnum, newnum, changenum, type, giftname, remark, "
        "create_time FROM giftstore_log WHERE userid = 100000374 ORDER BY id DESC"
    )
    summary = build_tool_summary(
        tool="mysql_query",
        name="test-mysql",
        environment_key="default",
        params={"sql": sql, "limit": 20},
        target=None,
        returned=20,
        elapsed_ms=135,
        error_code=None,
        client_prefix="client=cursor prefix=P2dc7BWnV8jL ",
    )

    detail = describe_summary("tool.call", summary)

    assert len(summary) <= 1024
    assert "params_truncated" not in summary
    assert detail["params_sql"] == sql
    assert ("limit", "20") in detail["params_fields"]
    assert detail["params_truncated"] is False


def test_huge_sql_is_cut_on_a_space_and_stays_redacted() -> None:
    secret = "SECRETVALUE"
    sql = f"SELECT '{secret}' AS token, " + " ".join(f"column_{index}" for index in range(400))

    class _Target:
        def __init__(self) -> None:
            self.secret = {"password": secret}

    summary = build_tool_summary(
        tool="mysql_query",
        name="test-mysql",
        environment_key="default",
        params={"sql": sql, "limit": 20, "db": None},
        target=_Target(),  # type: ignore[arg-type]
        returned=1,
        elapsed_ms=10,
        error_code=None,
        client_prefix="client=cursor prefix=abc ",
    )

    detail = describe_summary("tool.call", summary)

    assert len(summary) <= 1024
    assert secret not in summary
    assert detail["kind"] == "tool"
    assert detail["params_truncated"] is True
    assert ("limit", "20") in detail["params_fields"]
    assert detail["params_sql"].startswith("SELECT '***'")
    assert sql.replace(secret, "***").startswith(detail["params_sql"])
