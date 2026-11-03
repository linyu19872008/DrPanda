"""网页上的钟面时间。

库存和接口继续用 UTC。页面先写出 UTC 文字和机器可读的时刻，
浏览器再按本地时区改显示文字；悬停仍保留 UTC。
"""

from __future__ import annotations

from datetime import UTC, datetime

from markupsafe import Markup, escape


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utc_text(value: datetime | None, *, seconds: bool = False) -> str | None:
    if value is None:
        return None
    pattern = "%Y-%m-%d %H:%M:%S UTC" if seconds else "%Y-%m-%d %H:%M UTC"
    return as_utc(value).strftime(pattern)


def utc_instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_time(value: datetime | None, seconds: bool = False, extra: str = "") -> Markup:
    """供模板使用。无脚本时文字仍是 UTC。"""
    text = utc_text(value, seconds=seconds)
    instant = utc_instant(value)
    if text is None or instant is None:
        return Markup("")
    seconds_attr = ' data-seconds="true"' if seconds else ""
    suffix = f" {extra}" if extra else ""
    return Markup(
        f'<time datetime="{escape(instant)}" title="{escape(text)}"{seconds_attr}{suffix}>{escape(text)}</time>'
    )
