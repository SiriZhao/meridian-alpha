from datetime import UTC, datetime
from decimal import Decimal

from meridian.daily_release import offline_v1_soak, package_daily_run
from meridian.long_shadow import (
    ExecutionAssumption,
    OutcomeHorizon,
    ShadowPerformanceLedger,
    ShadowPerformanceRecord,
)
from meridian.profiles import RuntimeProfile, parse_profile
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    DailyDecision,
    FreshnessState,
    RunStatus,
)


def _account() -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="gate6h-test-account",
        account_alias="sanitized-fixture",
        provider="fixture",
        as_of=datetime(2026, 8, 31, 14, 30, tzinfo=UTC),
        total_equity=Decimal("10000"),
        cash=Decimal("10000"),
        sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )


def _decision() -> DailyDecision:
    as_of = datetime(2026, 8, 31, 14, 30, tzinfo=UTC)
    return DailyDecision(
        run_id="gate6h-test-run",
        as_of=as_of,
        account_snapshot_status=FreshnessState.VERIFIED,
        account_sync_state=AccountSyncState.SYNCED,
        market_data_status=FreshnessState.UNKNOWN,
        regime="UNKNOWN",
        warnings=("TEST_FIXTURE_ONLY",),
        blocked_reasons=("Market data unavailable.",),
        overall_status=RunStatus.DRAFT,
    )


def test_daily_package_is_sanitized_and_append_only(tmp_path) -> None:
    report = package_daily_run(_decision(), _account(), root=tmp_path, profile=RuntimeProfile.TEST)
    package = tmp_path / report["artifact_directory"]
    assert (package / "manifest.json").is_file()
    assert (package / "provider-health.json").is_file()
    assert (package / "evidence-lineage.json").is_file()
    assert (package / "target-portfolio.json").is_file()
    assert "SHADOW / NOT AUTHORIZED FOR ENTRY" in (package / "report.md").read_text(encoding="utf-8")
    attribution = report["attribution"]
    assert isinstance(attribution, dict)
    assert str(attribution["status"]).startswith("INSUFFICIENT_SAMPLE")
    shadow_ledger = report["shadow_ledger"]
    assert isinstance(shadow_ledger, dict)
    assert shadow_ledger["outcomes_are_not_fills"] is True




def test_performance_ledger_rejects_tampered_content_hash(tmp_path) -> None:
    path = tmp_path / "performance.json"
    ledger = ShadowPerformanceLedger(path)
    ledger.add(ShadowPerformanceRecord(
        run_id="r", ticker="AAPL", decision_as_of=_account().as_of,
        horizon=OutcomeHorizon.D1, recommendation_weight=Decimal("0.1"),
        target_weight=Decimal("0.1"), execution_assumption=ExecutionAssumption.NEXT_SESSION_OPEN,
    ))
    raw = path.read_text(encoding="utf-8").replace("content_hash", "content_hash", 1)
    raw = raw.replace('"content_hash":"', '"content_hash":"' + "0", 1)
    path.write_text(raw, encoding="utf-8")
    try:
        ShadowPerformanceLedger(path)
    except ValueError as error:
        assert "CORRUPT" in str(error)
    else:
        raise AssertionError("tampered performance ledger must fail closed")
def test_v1_soak_has_no_network_and_profiles_have_no_auto_execution() -> None:
    result = offline_v1_soak(cycles=200)
    assert result["status"] == "PASS"
    assert result["network_calls"] == 0
    assert parse_profile("manual_decision_support") is RuntimeProfile.MANUAL_DECISION_SUPPORT
    try:
        parse_profile("AUTO_EXECUTION")
    except ValueError as error:
        assert "AUTO_EXECUTION" in str(error)
    else:
        raise AssertionError("AUTO_EXECUTION must not be a supported profile")
