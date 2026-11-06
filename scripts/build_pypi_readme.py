#!/usr/bin/env python3
"""Generate README.pypi.md from README.md.

PyPI does not resolve relative links/images, so the package long description
uses GitHub absolute URLs. The repository README stays relative for local and
GitHub rendering.

Usage:
    python scripts/build_pypi_readme.py          # regenerate
    python scripts/build_pypi_readme.py --check  # fail if stale
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/linyu19872008/dr-panda-mcp"
RAW = "https://raw.githubusercontent.com/linyu19872008/dr-panda-mcp/main"
SOURCE = ROOT / "README.md"
TARGET = ROOT / "README.pypi.md"

ROOT_FILES = {
    "LICENSE",
    "CONTRIBUTING.md",
    "CONTRIBUTING.zh-CN.md",
    "SECURITY.md",
    "SECURITY.zh-CN.md",
    "CODE_OF_CONDUCT.md",
    "CODE_OF_CONDUCT.zh-CN.md",
    "CHANGELOG.md",
    "CHANGELOG.zh-CN.md",
    "README.zh-CN.md",
    ".env.example",
}


def absolute_url(target: str) -> str:
    target = target.strip()
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return target
    if target.startswith("docs/"):
        path = target.removeprefix("docs/")
        if target.endswith("/"):
            return f"{REPO}/tree/main/docs/{path}"
        return f"{REPO}/blob/main/docs/{path}"
    if target in ROOT_FILES:
        return f"{REPO}/blob/main/{target}"
    return target


def image_url(target: str) -> str:
    target = target.strip()
    if target.startswith("docs/"):
        return f"{RAW}/{target}"
    return target


def rewrite(text: str) -> str:
    # HTML images first (badges, logo, screenshots).
    text = re.sub(
        r'(<img[^>]*\bsrc=")([^"]+)(")',
        lambda match: match.group(1) + image_url(match.group(2)) + match.group(3),
        text,
    )
    # Markdown images.
    text = re.sub(
        r'(!\[[^\]]*\]\()([^)\s]+)(\))',
        lambda match: match.group(1) + image_url(match.group(2)) + match.group(3),
        text,
    )
    # HTML anchors to repository files/pages.
    text = re.sub(
        r'(<a[^>]*\bhref=")([^"]+)(")',
        lambda match: match.group(1) + absolute_url(match.group(2)) + match.group(3),
        text,
    )
    # Markdown links to repository files/pages.
    text = re.sub(
        r'(\[[^\]]*\]\()([^)\s]+)(\))',
        lambda match: match.group(1) + absolute_url(match.group(2)) + match.group(3),
        text,
    )
    return text


def build() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    body = rewrite(source)
    header = "<!-- Generated from README.md by scripts/build_pypi_readme.py. Do not edit by hand. -->\n\n"
    return header + body


def main() -> int:
    content = build()
    if "--check" in sys.argv[1:]:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print("README.pypi.md is stale; run python scripts/build_pypi_readme.py")
            return 1
        print("README.pypi.md is up to date")
        return 0
    TARGET.write_text(content, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
