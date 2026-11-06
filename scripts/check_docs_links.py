#!/usr/bin/env python3
"""Check relative links and images in repository markdown files.

Only local paths are checked; http(s)/mailto anchors are skipped so CI does not
depend on external sites. Run from the repository root:
    python scripts/check_docs_links.py
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "README.md",
    "README.zh-CN.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.zh-CN.md",
    "SECURITY.md",
    "SECURITY.zh-CN.md",
    "CODE_OF_CONDUCT.md",
    "CODE_OF_CONDUCT.zh-CN.md",
    "CHANGELOG.md",
    "CHANGELOG.zh-CN.md",
    "docs/README.md",
    "docs/architecture.md",
    "docs/security.md",
    "docs/ui-design.md",
    "docs/verification.md",
]
FILES += sorted(
    path.relative_to(ROOT).as_posix()
    for path in (ROOT / "docs").rglob("*.md")
    if path.name not in {Path(name).name for name in FILES}
)
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_LINK = re.compile(r'(?:src|href)="([^"]+)"')


def targets(text: str) -> list[str]:
    found = [match.group(1) for match in MD_LINK.finditer(text)]
    found += [match.group(1) for match in HTML_LINK.finditer(text)]
    return found


def check() -> list[str]:
    problems: list[str] = []
    for name in FILES:
        path = ROOT / name
        if not path.is_file():
            problems.append(f"{name}: file is missing")
            continue
        text = path.read_text(encoding="utf-8")
        for raw in targets(text):
            target = raw.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:", "tel:", "data:", "//")):
                continue
            local = unquote(urlsplit(target).path)
            if not local or local.startswith("/"):
                continue
            resolved = (path.parent / local).resolve()
            if not resolved.exists():
                problems.append(f"{name}: broken link {target}")
    return problems


def main() -> int:
    problems = check()
    if problems:
        print("Broken documentation links:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"OK: checked {len(FILES)} markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
