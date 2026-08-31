"""Build a deterministic, package-rooted Meridian Alpha Skill archive."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


def build(skill_dir: Path, output: Path) -> str:
    files = sorted(path for path in skill_dir.rglob("*") if path.is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(skill_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
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