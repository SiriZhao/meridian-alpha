from pathlib import Path

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
        "data_status": "PASS",
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
    assert result["status"] == "PAPER_BLOCKED"
    blockers = result["blockers"]
    assert isinstance(blockers, list)
    assert "PAPER_EXECUTION_BLOCKED_MARKET_CLOSED" in blockers
