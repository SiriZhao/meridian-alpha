"""Bounded offline scenario acceptance; timings are fixture measurements."""
from __future__ import annotations

import argparse
import json
import tempfile
import tracemalloc
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from meridian.canonical_run import assert_report_projection_consistency, seal_canonical_report
from meridian.config import load_policies
from meridian.daily_closure import DailyClosureService, persist_run_report
from meridian.run_health import build_run_health
from meridian.runtime import RuntimePaths
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState, MarketSnapshot


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(root: Path) -> dict[str, object]:
    policies = load_policies(Path(__file__).resolve().parents[1] / "policies")
    scenarios = {"uptrend": "DRAFT", "drawdown": "NO_ACTION", "sideways": "NO_ACTION",
                 "incomplete_quote": "NO_ACTION", "stale_market": "BLOCKED_STALE_MARKET",
                 "stale_account": "BLOCKED_STALE_ACCOUNT", "no_capital": "NO_CAPITAL", "small_capital": "NO_ACTION"}
    rows = []
    tracemalloc.start()
    try:
        for day in (datetime(2026, 10, 30, 15, tzinfo=UTC), datetime(2026, 11, 2, 16, tzinfo=UTC)):
            for scenario, expected in scenarios.items():
                cash = Decimal("0" if scenario == "no_capital" else "50" if scenario == "small_capital" else "10000")
                account = AccountSnapshot(snapshot_id="SYNTHETIC_" + scenario, account_alias="Schwab-Paper",
                    provider="SYNTHETIC_FIXTURE", as_of=day, total_equity=cash, cash=cash,
                    sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.STALE if scenario == "stale_account" else FreshnessState.VERIFIED)
                quote = MarketSnapshot(ticker="AAPL", timestamp=day - timedelta(hours=1) if scenario == "stale_market" else day,
                    last=Decimal("100"), previous_close=Decimal("99"), bid=Decimal("99.9"), ask=Decimal("100.1"),
                    volume=1000000, atr14=Decimal("2"), vwap=None if scenario == "incomplete_quote" else Decimal("100"),
                    daily_return=Decimal("-.05" if scenario == "drawdown" else "0" if scenario == "sideways" else ".05"),
                    gap_percent=Decimal(".01"), freshness_state=FreshnessState.VERIFIED)
                started = perf_counter()
                result = DailyClosureService(policies).run(account, {"AAPL": quote}, cutoff=day)
                require(result.decision.overall_status.value == expected, scenario + ": unexpected decision")
                require(result.report["broker_submission"] == "DISABLED", "broker boundary")
                repeat = DailyClosureService(policies).run(account, {"AAPL": quote}, cutoff=day)
                require(result.decision == repeat.decision and result.report == repeat.report, "replay drift")
                paths = RuntimePaths(root / day.date().isoformat() / scenario)
                snapshot = seal_canonical_report(result.report)
                persistence_started = perf_counter()
                json_path, markdown_path = persist_run_report(result.report, paths)
                persistence_ms = (perf_counter() - persistence_started) * 1000
                report = json.loads(json_path.read_text(encoding="utf-8"))
                health = build_run_health(report)
                assert_report_projection_consistency(report, markdown_path.read_text(encoding="utf-8"), health, report)
                require(snapshot.execution.broker_submission == "DISABLED" and not snapshot.execution.broker_side_effects, "authority invariant")
                rows.append({"session": day.date().isoformat(), "scenario": scenario, "status": expected,
                             "runtime_ms": round((perf_counter() - started) * 1000, 3),
                             "report_persistence_ms": round(persistence_ms, 3), "report_consistency": "PASS", "replay": "PASS"})
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"schema_version": "meridian-fixture-soak.v1", "status": "PASS", "measurement_class": "SYNTHETIC_OFFLINE_FIXTURE",
            "cycle_count": len(rows), "failure_count": 0, "unexpected_exception_count": 0,
            "traced_current_bytes": current, "traced_peak_bytes": peak,
            "memory_trend": "NOT_ESTIMATED_BOUNDED_SCENARIO_SAMPLE", "production_slo": "NOT_VERIFIED",
            "provider_latency": "NOT_MEASURED", "native_research_latency": "NOT_MEASURED", "model_invocations": 0,
            "broker_submission": "DISABLED", "canonical_runtime_written": False, "real_broker_side_effects": False, "cycles": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1] / ".tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase4-soak-", dir=base) as directory:
        report = run(Path(directory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cycles"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
