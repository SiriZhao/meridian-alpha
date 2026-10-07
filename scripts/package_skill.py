"""Build a deterministic, package-rooted Meridian Alpha Skill archive."""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import zipfile
from pathlib import Path

from meridian.runtime_io import atomic_write


def build(skill_dir: Path, output: Path) -> str:
    files = sorted(path for path in skill_dir.rglob("*") if (path.is_file() or path.is_symlink())
                   and "__pycache__" not in path.relative_to(skill_dir).parts and path.suffix not in {".pyc", ".pyo"})
    for path in files:
        if path.is_symlink() or any(part in {".git", ".venv", "venv", "runs", "var", "logs"} for part in path.relative_to(skill_dir).parts):
            raise ValueError("SKILL_PACKAGE_UNSAFE_PATH")
        if any(re.search(r"(?i)(^|[._-])(env|credentials?|secrets?|tokens?|passwords?)([._-]|$)", part) for part in path.relative_to(skill_dir).parts):
            raise ValueError("SKILL_PACKAGE_SECRET_LIKE_FILENAME")
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(skill_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    content = buffer.getvalue()
    atomic_write(output, content)
    digest = hashlib.sha256(content).hexdigest()
    atomic_write(output.with_suffix(".sha256"), f"{digest}  {output.name}\n")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-dir", type=Path, default=Path("skills/meridian-alpha"))
    parser.add_argument("--output", type=Path, default=Path("dist/meridian-alpha-skill-v1.zip"))
    args = parser.parse_args()
    digest = build(args.skill_dir, args.output)
    print(f"SKILL_ZIP={args.output.as_posix()}")
    print(f"SKILL_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
