from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = (Path("src/dr_panda_mcp/web/static/app.css")).read_text(encoding="utf-8")


def _block(selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", CSS, re.DOTALL)
    assert match is not None, f"找不到样式块 {selector}"
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", match.group(1)))


def _luminance(color: str) -> float:
    value = color.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _ratio(foreground: str, background: str) -> float:
    high, low = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


LIGHT = _block(":root")
DARK = _block(':root[data-theme="dark"]')

CONTRAST_PAIRS = [
    ("text", "bg", 4.5),
    ("text", "surface", 4.5),
    ("text-secondary", "surface", 4.5),
    ("text-muted", "surface", 4.5),
    ("text-muted", "surface-subtle", 4.5),
    ("accent", "surface", 4.5),
    ("accent-contrast", "accent", 4.5),
    ("danger", "danger-soft", 4.5),
    ("success", "success-soft", 4.5),
    ("warning", "warning-soft", 4.5),
]


@pytest.mark.parametrize(("theme", "tokens"), [("light", LIGHT), ("dark", DARK)])
def test_token_contrast(theme: str, tokens: dict[str, str]) -> None:
    for foreground, background, threshold in CONTRAST_PAIRS:
        ratio = _ratio(tokens[foreground], tokens[background])
        assert ratio >= threshold, f"{theme}: {foreground}/{background} 只有 {ratio:.2f}"


def test_both_themes_define_same_tokens() -> None:
    assert set(LIGHT) == set(DARK)
    assert len(LIGHT) >= 20


def test_theme_mechanism_has_no_js_flicker() -> None:
    assert "@media (prefers-color-scheme: dark)" in CSS
    assert ':root:not([data-theme="light"])' in CSS
    assert ':root[data-theme="dark"]' in CSS
    assert "color-scheme" in CSS


def test_accessibility_basics_in_css() -> None:
    assert ":focus-visible" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def test_no_external_assets() -> None:
    for pattern in ["@import", "url(http", "src=\"http", "href=\"http"]:
        assert pattern not in CSS
