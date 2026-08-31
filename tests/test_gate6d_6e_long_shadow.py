from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.finrlx_runtime import inspect_finrlx_runtime
from meridian.long_shadow import (
    ExecutionAssumption,
    OutcomeHorizon,
    ShadowPerformanceLedger,
    ShadowPerformanceRecord,
    ShadowRunLedger,
    ShadowRunRecord,
    SystemHealthLevel,
    derive_daily_health,
    run_historical_replay_battery,
    run_long_offline_soak,
)
from meridian.profiles import RuntimeProfile, parse_profile

T = datetime(2026, 8, 31, 14, 30, tzinfo=UTC)


def _run() -> ShadowRunRecord:
    return ShadowRunRecord(
        run_id="r1",
        decision_as_of=T,
        code_commit="commit",
        account_snapshot_hash="account-hash",
        security_master_hash="security-hash",
        quant_signals={"AAPL": Decimal("0.1")},
        final_alpha={"AAPL": Decimal("0.2")},
        target_weights={"AAPL": Decimal("0.25")},
        risk_result="PASS",
    )


def test_shadow_run_ledger_is_append_only_and_reloadable(tmp_path) -> None:
    ledger = ShadowRunLedger(tmp_path / "runs.json")
    ledger.append(_run())
    assert len(ShadowRunLedger(tmp_path / "runs.json").records) == 1
    with pytest.raises(ValueError, match="IMMUTABLE"):
        ledger.append(_run().model_copy(update={"risk_result": "FAIL"}))


def test_forward_outcome_is_not_available_before_observed_time() -> None:
    ledger = ShadowPerformanceLedger()
    row = ShadowPerformanceRecord(
        run_id="r1",
        ticker="AAPL",
        decision_as_of=T,
        horizon=OutcomeHorizon.D1,
        recommendation_weight=Decimal("0.25"),
        target_weight=Decimal("0.25"),
        execution_assumption=ExecutionAssumption.NEXT_SESSION_OPEN,
    )
    ledger.add(row)
    with pytest.raises(ValueError, match="NOT_YET_AVAILABLE"):
        ledger.join_forward_outcome(
            ("r1", "AAPL", OutcomeHorizon.D1),
            outcome_return=Decimal("0.01"),
            available_at=T + timedelta(days=1),
            observed_at=T + timedelta(hours=1),
        )


def test_replay_soak_health_and_profiles_are_explicit() -> None:
    assert run_historical_replay_battery().failed == 0
    assert run_long_offline_soak(cycles=50).network_calls == 0
    assert derive_daily_health({"account": "PASS", "quote": "UNAVAILABLE"}).level is SystemHealthLevel.RED
    assert parse_profile("shadow_live") is RuntimeProfile.SHADOW_LIVE
    with pytest.raises(ValueError, match="AUTO_EXECUTION"):
        parse_profile("AUTO_EXECUTION")


def test_finrlx_inspection_stays_unavailable_without_runtime() -> None:
    result = inspect_finrlx_runtime()
    assert result.status.value == "MODEL_UNAVAILABLE"
    assert result.imported_execution_surface is False

