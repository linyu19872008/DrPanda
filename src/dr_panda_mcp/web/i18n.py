"""Web i18n：语言解析、Cookie 与翻译函数。

英文是默认 UI 语言；``zh-Hans`` 通过 catalog 覆盖。模板/表单先用中文源文案
过渡，再逐步改为英文源；找不到翻译时回退源文案，避免页面出现空白。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "zh-Hans")
COOKIE_NAME = "drpanda_lang"
COOKIE_MAX_AGE = 365 * 24 * 3600
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_current: ContextVar[str] = ContextVar("drpanda_locale", default=DEFAULT_LOCALE)


@dataclass(frozen=True)
class LocaleOption:
    code: str
    label: str
    short: str


LOCALE_OPTIONS = (
    LocaleOption("en", "English", "EN"),
    LocaleOption("zh-Hans", "简体中文", "中文"),
)


def normalize_locale(value: str | None) -> str:
    raw = (value or "").strip().replace("_", "-").lower()
    if not raw:
        return DEFAULT_LOCALE
    if raw == "en" or raw.startswith("en-"):
        return "en"
    if raw in {"zh", "zh-hans", "zh-cn", "zh-sg"} or raw.startswith("zh-hans"):
        return "zh-Hans"
    return DEFAULT_LOCALE


def current_locale() -> str:
    return _current.get()


@contextmanager
def use_locale(locale: str) -> Iterator[None]:
    token = _current.set(normalize_locale(locale))
    try:
        yield
    finally:
        _current.reset(token)


def locale_from_request(request: Request | None) -> str:
    if request is None:
        return DEFAULT_LOCALE
    return normalize_locale(request.cookies.get(COOKIE_NAME))


def _load_catalog(locale: str) -> dict[str, str]:
    path = _LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("读取语言文件失败：%s", path, exc_info=True)
        return {}
    return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}


_CATALOGS = {code: _load_catalog(code) for code in SUPPORTED_LOCALES}


def _translate_label(label: str, catalog: dict[str, str]) -> str:
    return catalog.get(label, label)


def _dynamic_english(source: str, catalog: dict[str, str]) -> str | None:
    """Translate known validation templates without a Message object.

    This keeps the existing form error contract while covering the common
    parameterized validation messages. New code should prefer explicit keys.
    """
    match = re.match(r"^(.+)不能为空$", source)
    if match:
        return f"{_translate_label(match.group(1), catalog)} is required"
    match = re.match(r"^(.+)必须是整数$", source)
    if match:
        return f"{_translate_label(match.group(1), catalog)} must be an integer"
    match = re.match(r"^(.+)必须是 (.+) 之一$", source)
    if match:
        return f"{_translate_label(match.group(1), catalog)} must be one of {match.group(2)}"
    match = re.match(r"^(.+)必须是 (\d+)–(\d+) 的整数$", source)
    if match:
        return (
            f"{_translate_label(match.group(1), catalog)} must be an integer "
            f"between {match.group(2)} and {match.group(3)}"
        )
    match = re.match(r"^(\w+) 必须是 (\d+)–(\d+) 的整数$", source)
    if match:
        key = catalog.get(match.group(1), match.group(1))
        return f"{key} must be an integer between {match.group(2)} and {match.group(3)}"
    return None


def t(source: str, **params: Any) -> str:
    """翻译源文案；en 默认返回源，zh-Hans 查 catalog，缺失回退源。"""
    locale = current_locale()
    catalog = _CATALOGS.get(locale, {})
    template = catalog.get(source)
    if template is None and locale == "en":
        template = _dynamic_english(source, catalog)
    template = template or source
    try:
        return template.format(**params) if params else template
    except (KeyError, ValueError, IndexError):
        logger.warning("翻译占位符不匹配：%s", source)
        return template


def plural(source_one: str, source_other: str, count: int, **params: Any) -> str:
    """简单复数：中文只用一个形式；英文按 count 选择。"""
    source = source_one if count == 1 else source_other
    return t(source, count=count, **params)


def language_options() -> tuple[LocaleOption, ...]:
    return LOCALE_OPTIONS


def apply_language(response: Response, locale: str) -> Response:
    value = normalize_locale(locale)
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return response
