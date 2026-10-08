"""Daily integration cannot replace orders, widen authority or touch ledgers."""

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.config import load_policies
from meridian.daily_closure import DailyClosureService
from meridian.historical import HistoricalBarCertification
from meridian.quant.integration import (
    immutable_record,
    observe_shadow,
    persist_shadow,
    plan_paper_candidate,
    sufficient_engineering_evidence,
)
from meridian.quant.policy import QuantPolicy
from meridian.quant.portfolio import target_from_weights
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState, MarketSnapshot
from meridian.security import AssetType, SecurityMetadata
from tests.quant_helpers import cutoff, histories, risk_policy, synthetic_dataset
from tests.test_daily_closure import NOW, account, market

D = Decimal
ROOT = Path(__file__).parents[1]


def test_default_v1_and_shadow_are_order_identical():
    policies = load_policies(ROOT / "policies")
    baseline = DailyClosureService(policies).run(account(), market(), cutoff=NOW)
    shadow = DailyClosureService(policies, QuantPolicy(mode="QUANT_V2_SHADOW")).run(account(), market(), cutoff=NOW)
    assert shadow.decision == baseline.decision
    assert shadow.report["orders"] == baseline.report["orders"]
    payload = shadow.report["quant_shadow"]
    assert isinstance(payload, dict) and payload["status"] == "INSUFFICIENT_DATA"
    assert "quant_shadow" not in baseline.report


def test_shadow_symbol_mismatch_isolated_and_stale_gates_preserved():
    policies = load_policies(ROOT / "policies")
    history = histories(synthetic_dataset())
    service = DailyClosureService(policies, QuantPolicy(mode="QUANT_V2_SHADOW"))
    result = service.run(account(), market(), cutoff=NOW, quant_history={"MSFT": history["AAPL"]})
    assert result.decision.orders
    payload = result.report["quant_shadow"]
    assert isinstance(payload, dict) and payload["status"] == "SHADOW_BLOCKED"
    stale = service.run(account(freshness=FreshnessState.STALE), market(), cutoff=NOW)
    assert not stale.decision.orders


def test_canonical_closure_refuses_candidate_switch_even_with_flag():
    policies = load_policies(ROOT / "policies")
    approved = QuantPolicy(mode="QUANT_V2_PAPER_CANDIDATE", paper_approved=True, approval_reference="TEST_ONLY")
    result = DailyClosureService(policies, approved).run(account(), market(), cutoff=NOW)
    original = DailyClosureService(policies).run(account(), market(), cutoff=NOW)
    assert result.decision == original.decision
    payload = result.report["quant_shadow"]
    assert isinstance(payload, dict) and payload["status"] == "PAPER_REVIEW_REQUIRES_SEPARATE_CALL"


def test_shadow_explains_scores_risk_and_immutable_storage(tmp_path: Path):
    dataset = synthetic_dataset()
    when = cutoff(dataset)
    policies = load_policies(ROOT / "policies")
    policies = replace(policies, risk=risk_policy())
    snapshot = AccountSnapshot(snapshot_id="quant-synthetic", account_alias="PAPER_FIXTURE",
                               provider="SYNTHETIC", as_of=when, total_equity=D(100000), cash=D(100000),
                               sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.VERIFIED)
    policy = QuantPolicy(mode="QUANT_V2_SHADOW", strategy="A2", allocation="score")
    target = target_from_weights({"AAPL": D(".1")}, when, "baseline")
    record = observe_shadow(run_id="synthetic-shadow", cutoff=when, market_hash="fixture-snapshot",
                            account=snapshot, quotes={}, baseline_target=target, histories=histories(dataset),
                            policies=policies, policy=policy, diagnostic=True,
                            metadata={s: SecurityMetadata(s, AssetType.DIVERSIFIED_ETF, None, None) for s in policies.universe.tickers})
    assert record.status == "SHADOW_COMPUTED"
    assert record.scores and not record.paper_ledger_changed and not record.canonical_orders_changed
    path = persist_shadow(record, tmp_path)
    assert persist_shadow(record, tmp_path) == path
    assert json.loads(path.read_text(encoding="utf-8"))["authority"] == "SHADOW_ONLY"
    assert "account_alias" not in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="IMMUTABLE"):
        immutable_record(path, "changed")


def test_human_approval_and_oos_evidence_required(tmp_path: Path):
    from meridian.audit import AuditStore
    from meridian.paper import PaperLedger
    with pytest.raises(ValueError, match="APPROVAL"):
        QuantPolicy(mode="QUANT_V2_PAPER_CANDIDATE")
    store = AuditStore(tmp_path / "paper.sqlite3")
    ledger = PaperLedger(store)
    ledger.initialize()
    envelope = ledger.export_snapshot()
    policy = QuantPolicy(mode="QUANT_V2_PAPER_CANDIDATE", paper_approved=True, approval_reference="TEST_ONLY")
    result = plan_paper_candidate(envelope, {}, {}, envelope.as_of,
                                  load_policies(ROOT / "policies"), policy)
    assert result.status == "INSUFFICIENT_EVIDENCE" and not result.orders
    assert not result.ledger_changed
    assert not sufficient_engineering_evidence((), policy, load_policies(ROOT / "policies").risk)


def test_unknown_sector_is_rejected_in_shadow():
    dataset = synthetic_dataset()
    when = cutoff(dataset)
    snapshot = AccountSnapshot(snapshot_id="quant-synthetic", account_alias="PAPER_FIXTURE", provider="SYNTHETIC",
                               as_of=when, total_equity=D(100000), cash=D(100000), sync_state=AccountSyncState.SYNCED,
                               freshness_state=FreshnessState.VERIFIED)
    policies = load_policies(ROOT / "policies")
    record = observe_shadow(run_id="risk-test", cutoff=when, market_hash="fixture", account=snapshot, quotes={},
                            baseline_target=None, histories=histories(dataset), policies=policies,
                            policy=QuantPolicy(mode="QUANT_V2_SHADOW", strategy="A2"), diagnostic=True)
    assert any("missing security metadata" in v for v in record.risk_violations)
    assert all(s.new_target_weight == 0 for s in record.symbols)


def test_paper_candidate_passes_existing_planner_without_executing(tmp_path: Path, monkeypatch):
    # Certified inputs and prior review are mocked contracts, not real market
    # evidence. The test exercises the planner boundary with a disposable ledger.
    from datetime import UTC, datetime, timedelta

    import meridian.quant.integration as integration
    from meridian.audit import AuditStore
    from meridian.paper import PaperLedger
    from meridian.quant.backtest import QuantSecurityMetadata
    from meridian.trading_calendar import session_close

    dataset = synthetic_dataset()
    when = datetime.now(UTC)
    # Relocate a synthetic contract fixture to completed sessions before now;
    # no artifact from this test is counted as empirical evidence.
    from meridian.trading_calendar import is_trading_session, latest_completed_session
    final = latest_completed_session(when)
    dates = []
    cursor = final
    while len(dates) < 253:
        if is_trading_session(cursor):
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    history = {}
    for series in dataset.series:
        bars = tuple(bar.model_copy(update={"session": day, "observed_at": session_close(day),
                                            "available_at": session_close(day), "retrieved_at": when,
                                            "certification": HistoricalBarCertification.CERTIFIED_MARKET_SESSION})
                     for bar, day in zip(series.bars[:253], dates, strict=True))
        history[series.canonical_symbol] = series.model_copy(update={"bars": bars, "as_of": when, "source_mode": "TEST_CONTRACT_STUB"})
    ledger = PaperLedger(AuditStore(tmp_path / "isolated-paper.sqlite3"))
    ledger.initialize()
    envelope = ledger.export_snapshot(observed_at=when)
    policy = QuantPolicy(mode="QUANT_V2_PAPER_CANDIDATE", strategy="A2", allocation="score",
                         paper_approved=True, approval_reference="MOCK_REVIEW_ONLY")
    monkeypatch.setattr(integration, "sufficient_engineering_evidence", lambda *args: True)
    policies = load_policies(ROOT / "policies")
    quotes = {s: MarketSnapshot(ticker=s, timestamp=when, last=D(100), previous_close=D(99),
                                bid=D("99.9"), ask=D("100.1"), volume=1000000, atr14=D(2), vwap=D(100),
                                daily_return=D(".01"), freshness_state=FreshnessState.VERIFIED) for s in policies.universe.tickers}
    before = ledger.status()
    result = plan_paper_candidate(envelope, quotes, history, when, policies, policy,
                                  pit_metadata=tuple(QuantSecurityMetadata(symbol=s, asset_type="DIVERSIFIED_ETF", known_at=when, source="MOCK_METADATA_CONTRACT") for s in policies.universe.tickers))
    assert result.status == "READY_FOR_PAPER_REVIEW" and result.orders
    assert result.authority == "PAPER_REVIEW_ONLY_NOT_FOR_REAL_ENTRY"
    assert ledger.status() == before


def test_quant_cli_help_never_constructs_canonical_service(monkeypatch, capsys):
    from meridian.application_cli import main
    monkeypatch.setattr(sys, "argv", ["meridian", "quant", "--help"])
    def forbidden(*args, **kwargs):
        pytest.fail("quant CLI must not initialize canonical service")
    monkeypatch.setattr("meridian.application_cli.MeridianApplicationService", forbidden)
    with pytest.raises(SystemExit) as code:
        main()
    assert code.value.code == 0
    assert "--diagnostic" in capsys.readouterr().out


def test_quant_cli_rejects_unverified_real_input(tmp_path: Path):
    dataset = synthetic_dataset().model_copy(update={"evidence_status": "UNVERIFIED"})
    source = tmp_path / "dataset.json"
    source.write_text(dataset.stable_json(), encoding="utf-8")
    process = subprocess.run([sys.executable, "-m", "meridian", "quant", "inspect", "--dataset", str(source)],
                             capture_output=True, text=True, check=False)
    assert process.returncode == 0
    assert json.loads(process.stdout)["status"] == "UNVERIFIED"
