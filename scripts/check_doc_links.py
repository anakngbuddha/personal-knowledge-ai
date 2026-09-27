#!/usr/bin/env python3
"""Fail if a relative Markdown link points at a file that does not exist (audit finding 14)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SKIP_DIRS = {"node_modules", ".git", "graphify-out", ".venv", "venv"}


def main() -> int:
    broken: list[str] = []
    for md in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in md.parts):
            continue
        for target in LINK.findall(md.read_text(encoding="utf-8", errors="ignore")):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if path and not (md.parent / path).exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    for line in broken:
        print(f"broken link: {line}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
