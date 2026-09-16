from pathlib import Path
from typing import cast

from meridian.application import MeridianApplicationService
from meridian.runtime import RuntimePaths


def test_paper_execution_remains_blocked_when_research_is_complete(
    tmp_path: Path, monkeypatch
) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path / "runtime"))
    closed_daily = {
        "run_id": "daily-closed",
        "information_cutoff": "2026-09-12T16:00:00+00:00",
        "analysis_time": "2026-09-12T16:00:00+00:00",
        "trading_date": "2026-09-12",
        "status": "NO_ACTION",
        "runtime_status": "PASS",
        "data_status": "MARKET_CLOSED",
        "market_data_tradeable": False,
        "research_status": "AVAILABLE",
        "market_observations": {},
        "portfolio": None,
        "readiness": {},
        "manual_authority": {},
        "research": {"context": {"status": "AVAILABLE"}},
        "decision": {},
        "startup_diagnostics": {"market_status": {"status": "CLOSED"}},
    }
    monkeypatch.setattr(service, "daily", lambda *args, **kwargs: closed_daily)
    result = service.paper_run()
    assert result["status"] == "PAPER_WAITING_FOR_MARKET"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "PAPER_EXECUTION_BLOCKED_MARKET_CLOSED" in blockers
    market = cast(dict[str, object], result["market"])
    paper_execution = cast(dict[str, object], result["paper_execution"])
    assert market["market_data_tradeable"] is False
    assert paper_execution["fills"] == []


def test_open_market_with_stale_data_remains_blocked(tmp_path: Path, monkeypatch) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path / "runtime"))
    stale_daily = {
        "run_id": "daily-open-stale",
        "information_cutoff": "2026-09-08T14:00:00+00:00",
        "analysis_time": "2026-09-08T14:00:00+00:00",
        "trading_date": "2026-09-08",
        "status": "BLOCKED_STALE_MARKET",
        "runtime_status": "PASS",
        "data_status": "FAILED",
        "market_data_tradeable": False,
        "research_status": "AVAILABLE",
        "market_observations": {},
        "portfolio": None,
        "readiness": {},
        "manual_authority": {},
        "research": {"context": {"status": "AVAILABLE"}},
    }
    monkeypatch.setattr(service, "daily", lambda *args, **kwargs: stale_daily)
    result = service.paper_run()
    assert result["status"] == "PAPER_BLOCKED"
    stale_blockers = cast(list[object], result["blockers"])
    assert "PAPER_EXECUTION_BLOCKED_MARKET_DATA" in stale_blockers
    market = cast(dict[str, object], result["market"])
    paper_execution = cast(dict[str, object], result["paper_execution"])
    assert market["market_data_tradeable"] is False
    assert paper_execution["fills"] == []


