from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from test_recommendation_readiness import envelope

from meridian.application import MeridianApplicationService
from meridian.audit import AuditStore
from meridian.host_readiness import inspect_snapshot
from meridian.runtime import RuntimePaths


def test_missing_and_duplicate_daily_persist_readiness(tmp_path: Path) -> None:
    paths = RuntimePaths(tmp_path / "runtime # 中文")
    app = MeridianApplicationService(paths)
    missing = app.daily(None)
    assert missing["runtime_status"] == "PASS"
    readiness = missing["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["recommendation_readiness"] == "BLOCKED"
    assert missing["blocked_reasons"] == ["ACCOUNT_SNAPSHOT_MISSING"]
    now = datetime.now(UTC)
    path = envelope(tmp_path / "fixture.json", now)
    # Reserve exactly this snapshot, as an earlier process would have done.
    diag, _ = inspect_snapshot(path, max_age_seconds=3600)
    assert diag.snapshot_key and diag.content_hash
    AuditStore(paths.db).snapshot_novelty(diag.snapshot_key, diag.content_hash, seen_at=now.isoformat())
    duplicate = app.daily(path)
    assert duplicate["blocked_reasons"] == ["ACCOUNT_SNAPSHOT_REPLAYED"]
    assert duplicate["orders"] == []
    assert "Recommendation readiness" in Path(str(duplicate["report_markdown"])).read_text(encoding="utf-8")
    with closing(sqlite3.connect(paths.db)) as connection:
        rows = connection.execute("SELECT payload_json FROM run_readiness").fetchall()
        assert len(rows) == 2
        for row in rows:
            assert json.loads(row[0])["readiness"]["recommendation_readiness"] == "BLOCKED"
            assert '"cash"' not in row[0]



def test_invalid_market_fixture_persists_blockers(tmp_path: Path) -> None:
    app = MeridianApplicationService(RuntimePaths(tmp_path / "runtime"))
    account = envelope(tmp_path / "account.json", datetime.now(UTC))
    market = tmp_path / "invalid-market.json"
    market.write_text("invalid", encoding="utf-8")
    result = app.daily(account, market)
    assert result["exit_code"] == 3
    assert result["error_code"] == "MARKET_FIXTURE_INVALID"
    assert result["orders"] == []
    readiness = result["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["recommendation_readiness"] == "BLOCKED"
    assert readiness["quote_certification_status"] == "BLOCKED"
    assert Path(str(result["report_json"])).exists()
