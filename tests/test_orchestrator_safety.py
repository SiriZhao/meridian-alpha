from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.config import load_policies
from meridian.market import Bar, FakeMarketDataProvider
from meridian.orchestrator import DailyOrchestrator
from meridian.research import FakeResearchEngine
from meridian.schemas import (
    AccountSnapshot,
    AgentSignal,
    EvidenceItem,
    FreshnessState,
    Holding,
    MarketSnapshot,
    RunStatus,
)

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)
TICKERS = ("AAPL", "MSFT", "NVDA", "SPY")


def account(name: str) -> AccountSnapshot:
    return AccountSnapshot.model_validate_json(
        (ROOT / "schemas" / "examples" / name).read_text(encoding="utf-8")
    )


def quote(ticker: str, freshness: FreshnessState = FreshnessState.VERIFIED) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        timestamp=AS_OF,
        last=Decimal("200"),
        bid=Decimal("199"),
        ask=Decimal("201"),
        previous_close=Decimal("198"),
        volume=1000,
        atr14=Decimal("5"),
        vwap=Decimal("200"),
        daily_return=Decimal("0.01"),
        gap_percent=Decimal("0"),
        freshness_state=freshness,
    )


def history() -> tuple[Bar, ...]:
    return (
        Bar(
            AS_OF - timedelta(days=1),
            Decimal("198"),
            Decimal("200"),
            Decimal("197"),
            Decimal("198"),
            1000,
        ),
        Bar(AS_OF, Decimal("199"), Decimal("201"), Decimal("198"), Decimal("200"), 1200),
    )


def signal(ticker: str) -> AgentSignal:
    return AgentSignal(
        ticker=ticker,
        as_of=AS_OF,
        direction="BULLISH",
        conviction=Decimal("0.8"),
        fundamental_score=Decimal("0.8"),
        technical_score=Decimal("0.3"),
        risk_score=Decimal("0.1"),
        thesis="test",
        evidence=(
            EvidenceItem(
                source="synthetic-fixture",
                observed_at=AS_OF,
                evidence_type="fixture",
                summary="Synthetic fixture",
            ),
        ),
        source="fake",
    )


class NoCallMarket:
    provider_name = "no-call"

    def get_quote(self, ticker: str) -> MarketSnapshot:
        raise AssertionError("zero capital must not fetch quotes")

    def get_history(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> tuple[Bar, ...]:
        raise AssertionError("zero capital must not fetch history")

    def get_market_snapshot(self, ticker: str, as_of: datetime) -> MarketSnapshot:
        raise AssertionError("zero capital must not fetch market snapshots")

    def get_benchmark_snapshot(self) -> MarketSnapshot:
        raise AssertionError("zero capital must not fetch benchmark")

    def get_volatility_context(self) -> dict[str, Decimal]:
        raise AssertionError("zero capital must not fetch volatility")


def test_zero_capital_does_not_call_market_or_research() -> None:
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), NoCallMarket(), FakeResearchEngine({})
    ).run(account("empty-zero.json"), AS_OF)
    assert result.overall_status is RunStatus.NO_CAPITAL
    assert result.orders == ()


def test_missing_market_data_is_draft_without_orders() -> None:
    provider = FakeMarketDataProvider({"AAPL": quote("AAPL")})
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), provider, FakeResearchEngine({})
    ).run(account("empty-50000.json"), AS_OF)
    assert result.overall_status is RunStatus.DRAFT
    assert result.orders == ()


def test_missing_research_is_draft_without_orders() -> None:
    provider = FakeMarketDataProvider(
        {ticker: quote(ticker) for ticker in TICKERS},
        {ticker: history() for ticker in TICKERS},
    )
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), provider, FakeResearchEngine({})
    ).run(account("empty-50000.json"), AS_OF)
    assert result.overall_status is RunStatus.DRAFT
    assert result.orders == ()


def test_complete_synthetic_pipeline_is_ready_only_with_all_inputs() -> None:
    provider = FakeMarketDataProvider(
        {ticker: quote(ticker) for ticker in TICKERS},
        {ticker: history() for ticker in TICKERS},
    )
    engine = FakeResearchEngine({ticker: signal(ticker) for ticker in TICKERS})
    result = DailyOrchestrator(load_policies(ROOT / "policies"), provider, engine).run(
        account("empty-50000.json"), AS_OF
    )
    # A generic adapter returning an un-certified AgentSignal cannot reach
    # the executable daily decision boundary.
    assert result.overall_status is RunStatus.DRAFT
    assert result.target_portfolio is None
    assert result.orders == ()


def test_naive_run_date_is_rejected_before_work() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DailyOrchestrator(
            load_policies(ROOT / "policies"), NoCallMarket(), FakeResearchEngine({})
        ).run(account("empty-50000.json"), AS_OF.replace(tzinfo=None))


def test_future_account_snapshot_is_failed() -> None:
    future = account("empty-50000.json").model_copy(update={"as_of": AS_OF + timedelta(minutes=1)})
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), NoCallMarket(), FakeResearchEngine({})
    ).run(future, AS_OF)
    assert result.overall_status is RunStatus.FAILED


def test_universe_excluded_holding_requires_a_current_quote() -> None:
    current = account("empty-50000.json").model_copy(
        update={
            "holdings": (
                Holding(
                    ticker="TSLA",
                    quantity=Decimal("1"),
                    market_value=Decimal("200"),
                    price=Decimal("200"),
                ),
            ),
            "cash": Decimal("49800"),
        }
    )
    provider = FakeMarketDataProvider(
        {ticker: quote(ticker) for ticker in TICKERS},
        {ticker: history() for ticker in TICKERS},
    )
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), provider, FakeResearchEngine({})
    ).run(current, AS_OF)
    assert result.overall_status is RunStatus.DRAFT
    assert result.orders == ()
