from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell packaging helper is Windows-only")
def test_review_archive_excludes_secret_and_runtime_paths(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("safe", encoding="utf-8")
    (root / ".env.local").write_text("synthetic-secret", encoding="utf-8")
    (root / ".env").write_text("synthetic-secret", encoding="utf-8")
    for directory in (
        ".git",
        ".venv",
        "vendor_cache",
        "secrets",
        "credentials",
        "var",
        "logs",
        "cache",
        "__pycache__",
    ):
        path = root / directory
        path.mkdir()
        (path / "hidden.txt").write_text("excluded", encoding="utf-8")
    (root / "state.sqlite3").write_text("excluded", encoding="utf-8")
    for filename in ("private.pem", "client.p12", "signing.key", "secret-token.txt"):
        (root / filename).write_text("excluded", encoding="utf-8")
    archive = tmp_path / "review.zip"
    manifest = tmp_path / "manifest.txt"
    script = Path(__file__).parents[1] / "scripts" / "package_review.ps1"
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-SourceRoot",
            str(root),
            "-OutputPath",
            str(archive),
            "-ManifestPath",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert "README.md" in names
    assert "REVIEW-MANIFEST.txt" in names
    assert manifest.is_file()
    assert ".env.local" not in manifest.read_text(encoding="utf-8")
    assert not any(
        name == ".env"
        or name.startswith(".env.")
        or any(
            part
            in {
                ".git",
                ".venv",
                "vendor_cache",
                "secrets",
                "credentials",
                "var",
                "logs",
                "cache",
                "__pycache__",
            }
            for part in Path(name).parts
        )
        or name.endswith((".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12", ".pfx"))
        or any(token in Path(name).name.lower() for token in ("secret", "token"))
        for name in names
    )
