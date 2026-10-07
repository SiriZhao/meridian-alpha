"""Portable archive isolation and deterministic publication."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.package_skill import build


def test_skill_archive_excludes_generated_bytecode_and_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("synthetic portable skill", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "generated.pyc").write_bytes(b"synthetic bytecode")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    assert build(source, first) == build(source, second)
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["SKILL.md"]
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize("filename", [".env", "credentials.json", "access-token.txt", "secrets/data.json"])
def test_skill_archive_rejects_sensitive_filenames_before_read(tmp_path: Path, filename: str) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / filename).parent.mkdir(parents=True, exist_ok=True)
    (source / filename).write_text("synthetic forbidden file", encoding="utf-8")
    with pytest.raises(ValueError, match="SECRET_LIKE_FILENAME"):
        build(source, tmp_path / "output.zip")
    assert not (tmp_path / "output.zip").exists()


