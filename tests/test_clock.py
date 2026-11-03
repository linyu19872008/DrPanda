"""网页钟面时间：HTML 仍带 UTC，并给出可换算的时刻。"""

from datetime import UTC, datetime, timedelta, timezone

from dr_panda_mcp.web.clock import local_time, utc_instant, utc_text


def test_local_time_keeps_utc_text_and_instant() -> None:
    value = datetime(2026, 11, 3, 7, 53, tzinfo=UTC)
    html = str(local_time(value, extra='class="muted small" data-test-time'))
    assert 'datetime="2026-11-03T07:53:00Z"' in html
    assert 'title="2026-11-03 07:53 UTC"' in html
    assert ">2026-11-03 07:53 UTC</time>" in html
    assert "data-test-time" in html
    assert utc_instant(value) == "2026-11-03T07:53:00Z"
    assert utc_text(value) == "2026-11-03 07:53 UTC"


def test_local_time_converts_offsets_and_keeps_seconds() -> None:
    value = datetime(2026, 11, 3, 15, 53, 8, tzinfo=timezone(timedelta(hours=8)))
    html = str(local_time(value, seconds=True))
    assert 'datetime="2026-11-03T07:53:08Z"' in html
    assert "2026-11-03 07:53:08 UTC" in html
    assert 'data-seconds="true"' in html


def test_missing_time_renders_nothing() -> None:
    assert str(local_time(None)) == ""
