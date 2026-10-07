"""Validate an extracted portable Meridian Alpha Skill package.

This utility intentionally uses only the Python standard library so it can run
before the full Meridian project is installed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ABSOLUTE = re.compile(r"(?:[A-Z]:" + r"[\\\\/]|^/" + "Users/|^/" + "home/)")
SECRET_NAME = re.compile(r"(?i)(^|[._-])(env|credentials?|secrets?|tokens?|passwords?)([._-]|$)")
LINK = re.compile(r"\]\(([^)]+)\)")
FORBIDDEN_DIRS = {".git", ".venv", "venv", "runs", "var", "logs", "__pycache__"}


def fail(message: str) -> int:
    print(f"SKILL_PACKAGE_INVALID: {message}")
    return 1


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    skill = root / "SKILL.md"
    if not skill.is_file():
        return fail("SKILL.md is missing")
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\nname: meridian-alpha\n" not in text:
        return fail("invalid frontmatter")
    if len(text.splitlines()) > 500:
        return fail("SKILL.md exceeds 500 lines")

    files = sorted(path for path in root.rglob("*") if path.is_file() or path.is_symlink())
    for path in files:
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            return fail(f"forbidden runtime path: {relative}")
        if any(SECRET_NAME.search(part) for part in relative.parts):
            return fail(f"secret-like filename: {relative}")
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            return fail(f"symlink escapes package: {relative}")
        if path.is_symlink():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return fail(f"unexpected binary file: {relative}")
        if ABSOLUTE.search(content):
            return fail(f"absolute path in {relative}")

    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "#")):
            continue
        target_path = (skill.parent / target.split("#", 1)[0]).resolve()
        if not target_path.is_relative_to(root) or not target_path.is_file():
            return fail(f"missing reference: {target}")

    print(f"SKILL_PACKAGE_VALID files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
