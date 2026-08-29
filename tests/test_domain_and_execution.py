from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.audit import AuditStore
from meridian.config import load_policies
from meridian.orders import LimitPriceEngine, OrderPlanner
from meridian.reconciliation import ReconciliationEngine
from meridian.risk import RiskEngine
from meridian.schemas import (
    AccountSnapshot,
    AgentSignal,
    DailyDecision,
    EvidenceItem,
    FreshnessState,
    MarketSnapshot,
    OrderDraft,
    RunStatus,
    Side,
    TargetPortfolio,
    TargetPosition,
)

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def policies():
    return load_policies(ROOT / "policies")


def account(name: str = "multi-stock.json") -> AccountSnapshot:
    return AccountSnapshot.model_validate_json(
        (ROOT / "schemas" / "examples" / name).read_text(encoding="utf-8")
    )


def quote(
    ticker: str = "AAPL",
    *,
    freshness: FreshnessState = FreshnessState.VERIFIED,
    bid: Decimal | None = Decimal("199"),
    ask: Decimal | None = Decimal("201"),
    vwap: Decimal | None = Decimal("200"),
    atr14: Decimal | None = Decimal("5"),
    gap: Decimal = Decimal("0"),
) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        timestamp=AS_OF,
        last=Decimal("200"),
        bid=bid,
        ask=ask,
        previous_close=Decimal("198"),
        volume=1_000_000,
        atr14=atr14,
        vwap=vwap,
        daily_return=Decimal("0.01"),
        gap_percent=gap,
        freshness_state=freshness,
    )


def target(*positions: tuple[str, Decimal]) -> TargetPortfolio:
    invested = sum((weight for _, weight in positions), Decimal("0"))
    return TargetPortfolio(
        as_of=AS_OF,
        cash_weight=Decimal("1") - invested,
        positions=tuple(
            TargetPosition(
                ticker=ticker,
                target_weight=weight,
                conviction=Decimal("0.8"),
                rationale="test",
            )
            for ticker, weight in positions
        ),
        allocator_name="test",
        allocator_version="1",
    )


def alpha(ticker: str, score: str) -> AgentSignal:
    direction = "BULLISH" if Decimal(score) > 0 else "NEUTRAL"
    return AgentSignal(
        ticker=ticker,
        as_of=AS_OF,
        direction=direction,
        conviction=Decimal("0.8"),
        fundamental_score=Decimal(score),
        thesis="test",
        evidence=(
            EvidenceItem(
                source="synthetic-fixture",
                observed_at=AS_OF,
                evidence_type="fixture",
                summary="Synthetic fixture",
            ),
        ),
        source="test",
    )


def test_domain_models_reject_naive_timestamps() -> None:
    payload = account("empty-50000.json").model_dump()
    payload["as_of"] = AS_OF.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        AccountSnapshot.model_validate(payload)
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketSnapshot.model_validate(
            {**quote().model_dump(), "timestamp": AS_OF.replace(tzinfo=None)}
        )


def test_model_invariants_reject_schema_drift() -> None:
    with pytest.raises(ValueError, match="bid must not exceed ask"):
        quote(bid=Decimal("202"), ask=Decimal("201"))
    with pytest.raises(ValueError, match="position weights plus cash_weight"):
        TargetPortfolio(
            as_of=AS_OF,
            cash_weight=Decimal("0.2"),
            positions=(
                TargetPosition(
                    ticker="AAPL",
                    target_weight=Decimal("0.2"),
                    conviction=Decimal("1"),
                    rationale="x",
                ),
            ),
            allocator_name="test",
            allocator_version="1",
        )
    with pytest.raises(ValueError, match="sell floor"):
        OrderDraft(
            ticker="AAPL",
            side=Side.BUY,
            quantity=Decimal("1"),
            min_acceptable_sell_price=Decimal("1"),
            target_weight=Decimal("0.1"),
            current_weight=Decimal("0"),
            estimated_notional=Decimal("1"),
            time_in_force="DAY",
            status=RunStatus.DRAFT,
            reason="x",
        )


def test_ready_decision_and_no_capital_final_validation() -> None:
    with pytest.raises(ValueError, match="ready decision requires a target"):
        DailyDecision(
            run_id="ready-without-target",
            as_of=AS_OF,
            account_snapshot_status=FreshnessState.VERIFIED,
            market_data_status=FreshnessState.VERIFIED,
            regime="NORMAL",
            overall_status=RunStatus.READY_FOR_MANUAL_ENTRY,
        )
    order = OrderDraft(
        ticker="AAPL",
        side=Side.BUY,
        quantity=Decimal("1"),
        target_weight=Decimal("0.1"),
        current_weight=Decimal("0"),
        estimated_notional=Decimal("200"),
        time_in_force="DAY",
        status=RunStatus.DRAFT,
        reason="x",
    )
    with pytest.raises(ValueError, match="NO_CAPITAL"):
        DailyDecision(
            run_id="capital-with-order",
            as_of=AS_OF,
            account_snapshot_status=FreshnessState.VERIFIED,
            market_data_status=FreshnessState.UNKNOWN,
            regime="NO_CAPITAL",
            orders=(order,),
            overall_status=RunStatus.NO_CAPITAL,
        )


def test_raw_agent_signal_cannot_enter_alpha_fusion() -> None:
    from meridian.alpha_fusion import fuse

    with pytest.raises(TypeError, match="CertifiedAgentSignal"):
        fuse(alpha("AAPL", "0"), Decimal("0"))


def test_risk_caps_position_and_sector() -> None:
    original = target(("AAPL", Decimal("0.3")), ("MSFT", Decimal("0.3")))
    report = RiskEngine().approve(
        original, account(), "NORMAL", policies().risk, {"AAPL": "TECH", "MSFT": "TECH"}
    )
    approved = {position.ticker: position.target_weight for position in report.approved.positions}
    assert approved["AAPL"] == Decimal("0.1")
    assert approved["MSFT"] == Decimal("0.1")
    assert report.approved.cash_weight >= policies().risk.min_cash_weight
    assert report.violations


def test_reconciliation_uses_actual_snapshot_and_never_oversells() -> None:
    current = account()
    reconciliation = ReconciliationEngine().reconcile(current, target())
    plan = OrderPlanner().plan(
        current,
        reconciliation,
        {"AAPL": quote("AAPL"), "MSFT": quote("MSFT")},
        policies().execution,
    )
    held = {holding.ticker: holding.quantity for holding in current.holdings}
    assert plan
    assert all(order.quantity <= held[order.ticker] for order in plan if order.side is Side.SELL)
    assert all(order.side is Side.SELL for order in plan)


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (quote(freshness=FreshnessState.STALE), RunStatus.BLOCKED_STALE_MARKET),
        (quote(bid=None), RunStatus.DRAFT),
        (quote(vwap=None), RunStatus.DRAFT),
        (quote(atr14=Decimal("0")), RunStatus.DRAFT),
        (quote(gap=Decimal("0.10")), RunStatus.DRAFT),
    ],
)
def test_limit_price_fail_closed(snapshot: MarketSnapshot, expected: RunStatus) -> None:
    result = LimitPriceEngine().calculate(Side.BUY, snapshot, policies().execution)
    assert result.status is expected
    if expected is not RunStatus.READY_FOR_MANUAL_ENTRY:
        assert result.preferred_limit is None


def test_audit_idempotency_rejects_contradictory_run(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    decision = DailyDecision(
        run_id="same-run",
        as_of=AS_OF,
        account_snapshot_status=FreshnessState.VERIFIED,
        market_data_status=FreshnessState.UNKNOWN,
        regime="NO_CAPITAL",
        overall_status=RunStatus.NO_CAPITAL,
    )
    store.write_decision(decision)
    store.write_decision(decision)
    assert len(store.list_runs()) == 1
    with pytest.raises(ValueError, match="contradictory"):
        store.write_decision(decision.model_copy(update={"warnings": ("changed",)}))
