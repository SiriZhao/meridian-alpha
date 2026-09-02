from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from meridian.config import load_policies
from meridian.daily_closure import DailyClosureService, load_snapshot, persist_report
from meridian.runtime import RuntimePaths
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    FreshnessState,
    MarketSnapshot,
    RunStatus,
)

NOW = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)
POLICIES = load_policies(Path(__file__).parents[1] / "policies")


def account(*, cash: str = "10000", freshness: FreshnessState = FreshnessState.VERIFIED) -> AccountSnapshot:
    return AccountSnapshot(snapshot_id="daily-closure-fixture", account_alias="sanitized-fixture", provider="fixture", as_of=NOW, total_equity=Decimal(cash), cash=Decimal(cash), sync_state=AccountSyncState.SYNCED, freshness_state=freshness)


def market(*, freshness: FreshnessState = FreshnessState.VERIFIED, timestamp: datetime = NOW) -> dict[str, MarketSnapshot]:
    return {"AAPL": MarketSnapshot(ticker="AAPL", timestamp=timestamp, last=Decimal("100"), bid=Decimal("99.90"), ask=Decimal("100.10"), previous_close=Decimal("99"), volume=1_000_000, atr14=Decimal("2"), vwap=Decimal("100"), daily_return=Decimal("0.05"), gap_percent=Decimal("0.01"), freshness_state=freshness)}


def test_fresh_path_generates_manual_draft_and_deterministic_audit(tmp_path: Path) -> None:
    service = DailyClosureService(POLICIES)
    first = service.run(account(), market(), cutoff=NOW)
    second = service.run(account(), market(), cutoff=NOW)
    assert first.decision.overall_status is RunStatus.DRAFT
    assert first.decision.orders and first.decision.orders[0].side.value == "BUY"
    assert first.report["execution"] == "MANUAL"
    assert first.report["broker_submission"] == "DISABLED"
    assert first.decision.run_id == second.decision.run_id
    saved = persist_report(first, RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)}))
    assert saved.report_json is not None and saved.report_json.is_file()
    assert "BROKER SUBMISSION = DISABLED" in saved.report_markdown.read_text(encoding="utf-8")  # type: ignore[union-attr]


def test_stale_missing_and_future_market_fail_closed() -> None:
    service = DailyClosureService(POLICIES)
    assert service.run(account(freshness=FreshnessState.STALE), market(), cutoff=NOW).decision.overall_status is RunStatus.BLOCKED_STALE_ACCOUNT
    assert service.run(account(), {}, cutoff=NOW).decision.overall_status is RunStatus.BLOCKED_STALE_MARKET
    assert service.run(account(), market(timestamp=NOW + timedelta(seconds=1)), cutoff=NOW).decision.orders == ()


def test_zero_capital_and_snapshot_sensitive_input_rejection(tmp_path: Path) -> None:
    assert DailyClosureService(POLICIES).run(account(cash="0"), market(), cutoff=NOW).decision.overall_status is RunStatus.NO_CAPITAL
    source = {"schema_version": "1", "snapshot_id": "bad", "source_kind": "fixture", "source_name": "fixture", "as_of": NOW.isoformat(), "retrieved_at": NOW.isoformat(), "coverage_status": "COMPLETE", "cash": "1", "total_equity": "1", "api_key": "must-reject"}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    try:
        load_snapshot(path, now=NOW, replay=True)
    except ValueError as error:
        assert "SENSITIVE" in str(error)
    else:
        raise AssertionError("sensitive snapshot input must be rejected")
