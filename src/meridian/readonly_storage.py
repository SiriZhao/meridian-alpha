"""Read-only SQLite inspection without creating WAL coordination files.

WAL databases are refused rather than opened as immutable: ignoring an active
WAL could silently discard committed account state. This guard assumes no
concurrent journal-mode reconfiguration; OS read-only permissions remain the
enforcement boundary against another process changing that mode concurrently.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


class ReadOnlyStorageRefusal(sqlite3.DatabaseError):
    """Sanitized storage refusal, distinct from corruption or migration errors."""


def _check_journal(path: Path) -> None:
    with path.open("rb") as source:
        header = source.read(20)
    if header[:16] != b"SQLite format 3\x00" or len(header) != 20:
        raise ReadOnlyStorageRefusal("READ_ONLY_DATABASE_HEADER_INVALID")
    if header[18:20] != b"\x01\x01" or any(
        Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ReadOnlyStorageRefusal("READ_ONLY_JOURNAL_REVIEW_REQUIRED")


def connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    _check_journal(resolved)
    connection = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        # Connecting is lazy. Recheck before the first SQLite statement.
        _check_journal(resolved)
        connection.execute("PRAGMA query_only=ON")
    except (OSError, sqlite3.Error):
        connection.close()
        raise
    return connection
