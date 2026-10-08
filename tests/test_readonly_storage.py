"""Local empty databases only: reading must not create coordination files."""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing

import pytest

from meridian import mcp_server
from meridian.audit import AuditStore
from meridian.live_account import ReadOnlyAuditStore
from meridian.readonly_storage import ReadOnlyStorageRefusal
from meridian.runtime import RuntimePaths
from meridian.runtime_diagnostics import _database


@pytest.mark.parametrize("journal", ["WAL", "-wal", "-shm", "-journal"])
def test_journal_inspection_refuses_without_side_effects(tmp_path, monkeypatch, journal):
    paths = RuntimePaths(tmp_path)
    store = AuditStore(paths.db)
    store.migrate()
    if journal == "WAL":
        with closing(sqlite3.connect(paths.db)) as connection:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        assert not paths.db.with_name(paths.db.name + "-wal").exists()
    else:
        paths.db.with_name(paths.db.name + journal).write_bytes(b"isolated engineering fixture")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.db.parent.iterdir()}
    with pytest.raises(ReadOnlyStorageRefusal, match="READ_ONLY_JOURNAL_REVIEW_REQUIRED"):
        ReadOnlyAuditStore(paths.db).get_decision_summary("fixture")
    result = _database(paths.db)
    assert result["status"] == "FAIL"
    assert result["detail"] == "READ_ONLY_JOURNAL_REVIEW_REQUIRED"
    assert result["migration_status"] == "NOT_VERIFIED"
    monkeypatch.setattr(mcp_server, "_store", lambda: ReadOnlyAuditStore(paths.db))
    assert mcp_server.get_run("fixture")["reason"] == "READ_ONLY_JOURNAL_REVIEW_REQUIRED"
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.db.parent.iterdir()}
    assert before == after


def test_ordinary_database_reads_and_rejects_writes(tmp_path):
    database = tmp_path / "ordinary.sqlite3"
    AuditStore(database).migrate()
    before = database.read_bytes()
    assert _database(database)["status"] == "PASS"
    assert ReadOnlyAuditStore(database).get_decision_summary("absent") is None
    with closing(ReadOnlyAuditStore(database).connect()) as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE forbidden (id INTEGER)")
    assert database.read_bytes() == before
    assert list(tmp_path.iterdir()) == [database]
