"""Offline acceptance with explicit synthetic inputs and a disposable paper ledger.

This validates persistence and projections, not live-market/GPT acceptance.
It never uses inherited runtime paths, provider credentials or network data.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from meridian.application import MeridianApplicationService
from meridian.canonical_run import assert_report_projection_consistency, canonical_snapshot
from meridian.report_bundle import verify_report_bundle
from meridian.runtime import RuntimePaths


class FixtureClock(datetime):
    """A declared offline OPEN session, independent of CI's wall clock."""
    @classmethod
    def now(cls, tz=None):
        value = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
        return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def fixture(mode: str) -> dict[str, object]:
    now = datetime.now(UTC)
    timestamp = now.isoformat()
    return {
        "run_id": "daily-safe-" + mode,
        "analysis_time": timestamp,
        "information_cutoff": timestamp,
        "trading_date": now.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
        "status": "NO_ACTION" if mode == "NO_ACTION" else "DRAFT",
        "runtime_status": "PASS", "data_status": "PASS", "research_status": "AVAILABLE",
        "portfolio": {"positions": [] if mode == "NO_ACTION" else [{"ticker": "AAPL", "target_weight": "0.10"}]},
        "market_observations": {
            symbol: {"last": price, "timestamp": timestamp, "freshness_state": "VERIFIED", "provider": "SYNTHETIC_ACCEPTANCE"}
            for symbol, price in (("AAPL", "100"), ("SPY", "500"))
        },
        "provider_probes": {"AAPL": {"selected_provider": "SYNTHETIC_ACCEPTANCE"}},
        "research": {"status": "AVAILABLE", "provider": "SYNTHETIC_ACCEPTANCE", "model": "NO_LLM_INVOCATION"},
        "decision_context": {"status": "AVAILABLE"}, "gates": [],
        "readiness": {"recommendation_readiness": "BLOCKED"},
        "manual_authority": {"status": "BLOCKED"}, "output_files": {},
    }


def accept(root: Path) -> dict[str, object]:
    # Freeze the disposable fixture clock; production session gates stay intact.
    canonical = Path("E:/MeridianAlphaRuntime").resolve()
    if root.resolve() == canonical or canonical in root.resolve().parents:
        raise RuntimeError("synthetic acceptance must not use canonical runtime")
    with patch("meridian.application.datetime", FixtureClock), patch(__name__ + ".datetime", FixtureClock):
        return _accept(root)


def _accept(root: Path) -> dict[str, object]:
    os.environ["MERIDIAN_HOME"] = str(root)
    os.environ["MERIDIAN_CACHE"] = str(root / "cache")
    results = []
    for mode, expected, count in (("NO_ACTION", "PAPER_NO_TRADE", 0), ("SYNTHETIC_FILL", "PAPER_READY", 1)):
        service = MeridianApplicationService(RuntimePaths(root / mode))
        require(service.paper_init()["status"] == "PAPER_INITIALIZED", "paper initialization")
        payload = fixture(mode)
        service.daily = lambda *args, _payload=payload, **kwargs: _payload  # type: ignore[method-assign]
        first = service.paper_run(run_purpose="ACCEPTANCE_VALIDATION")
        snapshot = canonical_snapshot(first)
        require(first["status"] == expected, "paper result")
        require(snapshot.execution.order_count == count and snapshot.execution.fill_count == count, "synthetic counts")
        require(snapshot.execution.broker_submission == "DISABLED" and not snapshot.execution.broker_side_effects, "broker boundary")
        paths = first["output_files"]
        require(isinstance(paths, dict), "report paths")
        if not isinstance(paths, dict):
            raise RuntimeError("report paths")
        verify_report_bundle(Path(str(paths["report_bundle_json"])))
        canonical = json.loads(Path(str(paths["paper_report_json"])).read_text(encoding="utf-8"))
        health = json.loads(Path(str(paths["run_health_json"])).read_text(encoding="utf-8"))
        markdown = Path(str(paths["paper_report_markdown"])).read_text(encoding="utf-8")
        assert_report_projection_consistency(canonical, markdown, health, first)
        duplicate = service.paper_run(run_purpose="ACCEPTANCE_VALIDATION")
        require(duplicate["status"] == "PAPER_ALREADY_EXECUTED", "duplicate owner")
        require(len(service.paper_trades()["trades"]) == count, "duplicate ledger mutation")  # type: ignore[arg-type]
        results.append({"scenario": mode, "status": expected, "orders": count, "fills": count, "duplicate": duplicate["status"]})
    environment = dict(os.environ, MERIDIAN_HOME=str(root / "NO_ACTION"), MERIDIAN_CACHE=str(root / "NO_ACTION" / "cache"), PYTHONPATH="")
    process = subprocess.run([sys.executable, "-m", "meridian", "paper", "status", "--json"], cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60)
    require(process.returncode == 0, "fresh-process CLI exit")
    require(json.loads(process.stdout)["broker_submission"] == "DISABLED", "fresh-process broker boundary")
    return {"status": "PASS", "input_mode": "SYNTHETIC_OFFLINE", "paper_scenarios": results, "fresh_process": "PASS", "report_consistency": "PASS", "broker_submission": "DISABLED", "real_broker_side_effects": False, "canonical_runtime_written": False}


def main() -> int:
    workspace = Path(__file__).resolve().parents[1]
    temporary_root = (workspace / ".tmp").resolve()
    require(workspace == temporary_root.parent, "acceptance temporary directory stays in workspace")
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="meridian-safe-acceptance-", dir=temporary_root) as directory:
        require(temporary_root in Path(directory).resolve().parents, "acceptance cleanup stays in workspace")
        print(json.dumps(accept(Path(directory)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
