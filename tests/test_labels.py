from __future__ import annotations

from dr_panda_mcp import errors
from dr_panda_mcp.web import labels


def test_error_labels_cover_every_error_code() -> None:
    assert set(labels.ERROR_LABELS) == set(errors.ALL_CODES)


def test_error_label_keeps_unknown_codes() -> None:
    assert labels.error_label("UPSTREAM_UNAVAILABLE") == "上游不可用"
    assert labels.error_label("SOMETHING_NEW") == "SOMETHING_NEW"
