from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from meridian.canonical_run import snapshot_from_legacy


def test_attribution_is_canonical_and_does_not_change_financial_result() -> None:
    from meridian.daily_closure import DailyClosureService
    from tests.test_daily_closure import NOW as CUTOFF
    from tests.test_daily_closure import POLICIES, account, market
    first = DailyClosureService(POLICIES).run(account(), market(), cutoff=CUTOFF)
    second = DailyClosureService(POLICIES).run(account(), market(), cutoff=CUTOFF)
    assert first.decision == second.decision
    canonical = snapshot_from_legacy(first.report)
    assert canonical.decision.attribution == first.report["decision_attribution"]
    attribution = canonical.decision.attribution
    assert attribution["research_in_score"] is False
    symbols = attribution["symbols"]
    assert isinstance(symbols, dict)
    row = symbols["AAPL"]
    assert row["raw_score"] == ".05" or row["raw_score"] == "0.05"
    assert row["target_before_risk"] == row["target_after_risk"]
    assert row["final_order_eligible"] and row["reason"] == "DRAFT"
    incomplete = market()
    incomplete["AAPL"] = incomplete["AAPL"].model_copy(update={"vwap": None})
    blocked = DailyClosureService(POLICIES).run(account(), incomplete, cutoff=CUTOFF)
    facts = snapshot_from_legacy(blocked.report).decision.attribution["symbols"]
    assert isinstance(facts, dict)
    assert facts["AAPL"]["reason"] == "ORDER_POLICY_REJECTED"
    assert not blocked.decision.orders and facts["AAPL"]["target_after_risk"] != "0"


def test_new_attribution_cross_artifact_contract_and_drift_detection() -> None:
    from meridian.canonical_run import (
        assert_report_projection_consistency,
        cli_summary,
        render_canonical_audit,
        seal_canonical_report,
    )
    from meridian.daily_closure import DailyClosureService
    from meridian.run_health import build_run_health
    from tests.test_daily_closure import NOW as CUTOFF
    from tests.test_daily_closure import POLICIES, account, market
    report = DailyClosureService(POLICIES).run(account(), market(), cutoff=CUTOFF).report
    canonical = seal_canonical_report(report)
    health = build_run_health(report)
    markdown = render_canonical_audit(canonical)
    cli = {**report, "summary": cli_summary(report)}
    assert_report_projection_consistency(report, markdown, health, cli)
    decision_health = health["decision"]
    assert isinstance(decision_health, dict)
    decision_health["attribution"] = {}
    with pytest.raises(AssertionError, match="ATTRIBUTION_DRIFT"):
        assert_report_projection_consistency(report, markdown, health, cli)


@pytest.mark.parametrize(("scenario", "expected"), [
    ("zero_signal", "NO_POSITIVE_SIGNAL"),
    ("negative_signal", "NO_POSITIVE_SIGNAL"),
    ("small_capital", "WHOLE_SHARE_ROUNDING"),
    ("cash_reserve", "CASH_RESERVE"),
    ("minimum_notional", "MINIMUM_NOTIONAL"),
])
def test_no_action_has_observed_reason(scenario: str, expected: str) -> None:
    from meridian.daily_closure import DailyClosureService
    from tests.test_daily_closure import NOW as CUTOFF
    from tests.test_daily_closure import POLICIES, account, market
    quotes = market()
    state = account(cash="500" if scenario == "small_capital" else "50" if scenario == "cash_reserve" else "10000")
    policies = POLICIES
    if scenario in {"zero_signal", "negative_signal"}:
        quotes["AAPL"] = quotes["AAPL"].model_copy(update={"daily_return": Decimal("0" if scenario == "zero_signal" else "-.05")})
    if scenario == "minimum_notional":
        policies = replace(POLICIES, execution=POLICIES.execution.model_copy(update={"minimum_order_notional": Decimal("2000")}))
    result = DailyClosureService(policies).run(state, quotes, cutoff=CUTOFF)
    facts = snapshot_from_legacy(result.report).decision.attribution["symbols"]
    assert isinstance(facts, dict)
    assert facts["AAPL"]["reason"] == expected
    assert result.decision.overall_status.value == "NO_ACTION" and not result.decision.orders


def test_positive_quant_can_be_removed_by_actual_sector_cap() -> None:
    from meridian.daily_closure import DailyClosureService
    from tests.test_daily_closure import NOW as CUTOFF
    from tests.test_daily_closure import POLICIES, account, market
    sample = market()["AAPL"]
    quotes = {symbol: sample.model_copy(update={"ticker": symbol}) for symbol in ("AAPL", "MSFT", "NVDA", "SPY")}
    result = DailyClosureService(POLICIES).run(account(), quotes, cutoff=CUTOFF)
    facts = snapshot_from_legacy(result.report).decision.attribution["symbols"]
    assert isinstance(facts, dict)
    assert facts["SPY"]["reason"] == "RISK_REDUCED_TO_ZERO"
    assert facts["SPY"]["raw_score"] == "0.05"
    assert facts["SPY"]["risk_constraints_applied"]

