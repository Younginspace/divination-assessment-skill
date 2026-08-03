#!/usr/bin/env python3
"""Check that every relative Markdown link in the Skill resolves locally."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


SKILL_ROOT = Path(__file__).resolve().parent.parent
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    errors: list[str] = []
    checked = 0
    for markdown_path in sorted(SKILL_ROOT.rglob("*.md")):
        text = markdown_path.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target_without_anchor = unquote(target.split("#", 1)[0])
            if not target_without_anchor:
                continue
            checked += 1
            resolved = (markdown_path.parent / target_without_anchor).resolve()
            try:
                resolved.relative_to(SKILL_ROOT)
            except ValueError:
                errors.append(
                    f"{markdown_path.relative_to(SKILL_ROOT)} -> {target} "
                    "(path escapes Skill root)"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"{markdown_path.relative_to(SKILL_ROOT)} -> {target}"
                )
    if errors:
        print("Broken local links:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS {checked} local Markdown links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
