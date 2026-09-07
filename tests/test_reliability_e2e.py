"""Windows-compatible subprocess smoke: no network or real account data."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def test_daily_fresh_and_existing_home_outside_checkout(tmp_path: Path) -> None:
    home = tmp_path / "运行 home #1"
    now = datetime.now(UTC).isoformat()
    account = tmp_path / "synthetic-account.json"
    account.write_text(json.dumps({
        "snapshot_id": "reliability-fixture", "source_kind": "fixture",
        "source_name": "synthetic-smoke", "as_of": now, "retrieved_at": now,
        "coverage_status": "COMPLETE", "cash": "10000", "total_equity": "10000",
    }), encoding="utf-8")
    market = tmp_path / "synthetic-market.json"
    market.write_text(json.dumps({"quotes": [{
        "ticker": "AAPL", "timestamp": now, "last": "100", "bid": "99.9",
        "ask": "100.1", "previous_close": "99", "volume": 1000000,
        "atr14": "2", "vwap": "100", "daily_return": "0.05",
        "gap_percent": "0.01", "freshness_state": "VERIFIED",
    }]}), encoding="utf-8")
    env = {**os.environ, "MERIDIAN_HOME": str(home), "PYTHONUTF8": "1"}
    for index in range(2):
        # Each daily run supplies new facts; duplicate protection is tested separately.
        payload = json.loads(account.read_text(encoding="utf-8"))
        payload["snapshot_id"] = f"reliability-fixture-{index}"
        payload["as_of"] = payload["retrieved_at"] = datetime.now(UTC).isoformat()
        account.write_text(json.dumps(payload), encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "-m", "meridian", "daily", "--snapshot", str(account),
             "--market-fixture", str(market), "--json"],
            cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=30, check=False,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        result = json.loads(run.stdout)
        assert result["runtime_status"] == "PASS"
        assert result["data_mode"] == "FIXTURE"
        assert result["research_status"] == "NOT_RUN"
        assert result["recommendation_status"] == "RESEARCH_ONLY"
        for path in result["output_files"].values():
            assert Path(path).is_relative_to(home) and Path(path).is_file()
        stored = json.loads(Path(result["report_json"]).read_text(encoding="utf-8"))
        assert stored["run_id"] == result["run_id"]
    with closing(sqlite3.connect(home / "db" / "meridian.sqlite3")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    doctor = subprocess.run([sys.executable, "-m", "meridian", "doctor", "--json"],
                            cwd=tmp_path, env=env, capture_output=True, text=True,
                            encoding="utf-8", timeout=20, check=False)
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert json.loads(doctor.stdout)["status"] == "PASS"


def test_future_schema_preserved_and_connections_released(tmp_path: Path) -> None:
    from meridian.application import MeridianApplicationService
    from meridian.runtime import RuntimePaths

    paths = RuntimePaths(tmp_path)
    app = MeridianApplicationService(paths)
    assert app.init()["status"] == "INIT_COMPLETE"
    with closing(sqlite3.connect(paths.db)) as connection, connection:
        connection.execute("INSERT INTO schema_migrations VALUES (99)")
        connection.execute("CREATE TABLE user_data (value TEXT)")
        connection.execute("INSERT INTO user_data VALUES ('preserve')")
    assert app.init()["status"] == "INIT_FAILED"
    with closing(sqlite3.connect(paths.db)) as connection:
        assert connection.execute("SELECT value FROM user_data").fetchone()[0] == "preserve"
    # Windows refuses this if any connection leaked from init/migrate/doctor.
    app.doctor()
    paths.db.rename(paths.db.with_suffix(".preserved"))


def test_live_retrieval_closes_cutoff_without_weakening_replay(monkeypatch) -> None:
    from datetime import timedelta

    import meridian.operational_data as data_module
    from meridian.operational_data import OperationalRefreshService
    from meridian.quotes import YahooChartQuoteProvider
    from meridian.security_master import DEFAULT_SECURITY_MASTER

    finished = datetime(2026, 9, 8, 14, tzinfo=UTC)
    started = finished - timedelta(seconds=2)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return finished.astimezone(tz or UTC)

    monkeypatch.setattr(data_module, "datetime", Clock)

    class Response:
        status = 200

        def read(self):
            return json.dumps({"chart": {"result": [{"meta": {
                "regularMarketPrice": 100,
                "regularMarketTime": started.timestamp(), "currency": "USD",
            }}]}}).encode()

    provider = YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER, opener=lambda *a, **k: Response(), clock=lambda: finished)
    refresh = OperationalRefreshService(provider, provider)
    replay = refresh.refresh("AAPL", analysis_time=started)
    assert replay.primary.status.value == "INVALID_RESPONSE"
    live = refresh.refresh("AAPL", analysis_time=started, live=True)
    assert live.primary.status.value == "OK"
    assert live.selected is not None
    assert live.selected.received_at <= live.information_cutoff <= live.analysis_time
