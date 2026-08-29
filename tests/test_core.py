from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.config import load_policies
from meridian.market import Bar, FakeMarketDataProvider, feature_set
from meridian.orchestrator import DailyOrchestrator
from meridian.research import FakeResearchEngine
from meridian.schemas import (
    AccountSnapshot,
    AgentSignal,
    EvidenceItem,
    FreshnessState,
    MarketSnapshot,
    RunStatus,
)

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def quote(ticker: str, last: str) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        timestamp=AS_OF,
        last=Decimal(last),
        bid=Decimal(last) - 1,
        ask=Decimal(last) + 1,
        previous_close=Decimal(last) - 2,
        volume=1_000_000,
        atr14=Decimal("5"),
        vwap=Decimal(last),
        daily_return=Decimal("0.01"),
        gap_percent=Decimal("0"),
        freshness_state=FreshnessState.VERIFIED,
    )


def signal(ticker: str) -> AgentSignal:
    return AgentSignal(
        ticker=ticker,
        as_of=AS_OF,
        direction="BULLISH",
        conviction=Decimal("0.9"),
        fundamental_score=Decimal("0.8"),
        technical_score=Decimal("0.5"),
        risk_score=Decimal("0.1"),
        thesis="Synthetic evidence-backed thesis.",
        risks=("Synthetic risk",),
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


def snapshot(name: str) -> AccountSnapshot:
    return AccountSnapshot.model_validate_json((ROOT / "schemas" / "examples" / name).read_text())


def test_zero_account_fails_closed_without_orders() -> None:
    account = snapshot("empty-zero.json")
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), FakeMarketDataProvider({}), FakeResearchEngine({})
    ).run(account, AS_OF)
    assert result.overall_status is RunStatus.NO_CAPITAL
    assert result.orders == ()


def test_stale_account_blocks_before_market_access() -> None:
    account = snapshot("empty-50000.json").model_copy(
        update={"freshness_state": FreshnessState.STALE}
    )
    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), FakeMarketDataProvider({}), FakeResearchEngine({})
    ).run(account, AS_OF)
    assert result.overall_status is RunStatus.BLOCKED_STALE_ACCOUNT


def test_no_lookahead_feature_gate() -> None:
    bars = tuple(
        Bar(
            timestamp=AS_OF + timedelta(days=offset),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal(str(100 + offset)),
            volume=100,
        )
        for offset in (-1, 0, 1)
    )
    features = feature_set(bars, AS_OF)
    assert features["daily_return"] == (Decimal("100") / Decimal("99")) - Decimal("1")


def test_synthetic_cash_account_generates_bounded_manual_drafts() -> None:
    account = snapshot("empty-50000.json")
    tickers = ("AAPL", "MSFT", "NVDA", "SPY")
    history = (
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
    provider = FakeMarketDataProvider(
        {
            "AAPL": quote("AAPL", "200"),
            "MSFT": quote("MSFT", "300"),
            "NVDA": quote("NVDA", "400"),
            "SPY": quote("SPY", "600"),
        },
        {ticker: history for ticker in tickers},
    )
    engine = FakeResearchEngine({ticker: signal(ticker) for ticker in tickers})
    result = DailyOrchestrator(load_policies(ROOT / "policies"), provider, engine).run(
        account, AS_OF
    )
    # Raw fixture AgentSignals are diagnostic-only after Gate 2.6; the
    # executable decision path fails closed until evidence certification.
    assert result.overall_status is RunStatus.DRAFT
    assert result.orders == ()
    assert result.target_portfolio is None


def test_policy_rejects_leverage(tmp_path: Path) -> None:
    target = tmp_path / "policies"
    target.mkdir()
    for source in (ROOT / "policies").iterdir():
        destination = target / source.name
        destination.write_text(source.read_text())
    risk = target / "risk.yaml"
    risk.write_text(risk.read_text().replace("allow_leverage: false", "allow_leverage: true"))
    with pytest.raises(ValueError, match="allow_leverage"):
        load_policies(target)
