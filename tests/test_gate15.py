from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.config import load_policies
from meridian.market import Bar, FakeMarketDataProvider
from meridian.orchestrator import DailyAnalysisService, DailyOrchestrator
from meridian.orders import ProjectedPortfolioValidator
from meridian.research import FakeResearchEngine
from meridian.schemas import (
    AccountSnapshot,
    AgentSignal,
    EvidenceItem,
    FreshnessState,
    MarketSnapshot,
    OrderDraft,
    RunStatus,
    Side,
)
from meridian.valuation import ValuedAccountState

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def policies():
    return load_policies(ROOT / "policies")


def account(name="empty-50000.json"):
    return AccountSnapshot.model_validate_json((ROOT / "schemas/examples" / name).read_text())


def quote(ticker="AAPL", timestamp=AS_OF, last=Decimal("200")):
    return MarketSnapshot(
        ticker=ticker,
        timestamp=timestamp,
        last=last,
        bid=last - Decimal("1"),
        ask=last + Decimal("1"),
        previous_close=last - Decimal("2"),
        volume=1000,
        atr14=Decimal("5"),
        vwap=last,
        daily_return=Decimal("0"),
        gap_percent=Decimal("0"),
        freshness_state=FreshnessState.VERIFIED,
    )


def test_account_age_boundaries():
    p = policies()
    max_age = p.data.account_snapshot_max_age_seconds
    for seconds, expected in [
        (max_age - 1, RunStatus.NO_CAPITAL),
        (max_age, RunStatus.NO_CAPITAL),
        (max_age + 1, RunStatus.BLOCKED_STALE_ACCOUNT),
    ]:
        a = account("empty-zero.json").model_copy(
            update={"as_of": AS_OF - timedelta(seconds=seconds)}
        )
        result = DailyOrchestrator(p, FakeMarketDataProvider({}), FakeResearchEngine({})).run(
            a, AS_OF
        )
        assert result.overall_status is expected


def test_quote_age_boundary_blocks_only_after_threshold():
    p = policies()
    age = p.data.quote_max_age_seconds
    history = (
        Bar(AS_OF - timedelta(days=1), Decimal("1"), Decimal("2"), Decimal("1"), Decimal("1"), 1),
        Bar(AS_OF, Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2"), 1),
    )
    for seconds, expected in [
        (age, RunStatus.DRAFT),
        (age + 1, RunStatus.BLOCKED_STALE_MARKET),
    ]:
        q = quote(timestamp=AS_OF - timedelta(seconds=seconds))
        tickers = ("AAPL", "MSFT", "NVDA", "SPY")
        provider = FakeMarketDataProvider(
            {ticker: q.model_copy(update={"ticker": ticker}) for ticker in tickers},
            {ticker: history for ticker in tickers},
        )
        a = account()
        signals = {
            ticker: AgentSignal(
                ticker=ticker,
                as_of=AS_OF,
                direction="BULLISH",
                conviction=Decimal("0.8"),
                fundamental_score=Decimal("0.5"),
                risk_score=Decimal("0.1"),
                thesis="x",
                source="fake",
                evidence=(
                    EvidenceItem(source="fixture", observed_at=AS_OF, evidence_type="fixture"),
                ),
            )
            for ticker in tickers
        }
        result = DailyOrchestrator(p, provider, FakeResearchEngine(signals)).run(a, AS_OF)
        assert result.overall_status is expected


def test_structured_evidence_validation():
    with pytest.raises(ValueError):
        AgentSignal(
            ticker="AAPL",
            as_of=AS_OF,
            direction="BULLISH",
            conviction=Decimal("1"),
            thesis="x",
            source="prod",
            evidence=(
                EvidenceItem(
                    source="s", observed_at=AS_OF + timedelta(seconds=1), evidence_type="news"
                ),
            ),
        )
    signal = AgentSignal(
        ticker="AAPL",
        as_of=AS_OF,
        direction="BULLISH",
        conviction=Decimal("1"),
        thesis="x",
        source="prod",
        evidence=(EvidenceItem(source="news", observed_at=AS_OF, evidence_type="news"),),
    )
    assert signal.evidence[0].source == "news"


def test_valuation_uses_fresh_mark_not_broker_value():
    a = account("multi-stock.json")
    q = {h.ticker: quote(h.ticker, last=Decimal("250")) for h in a.holdings}
    marked = ValuedAccountState.from_snapshot(a, q, Decimal("100000"))
    assert marked.value_for(a.holdings[0].ticker) == a.holdings[0].quantity * Decimal("250")
    assert marked.broker_reported_total_equity == a.total_equity


def test_projected_validator_rejects_oversell_and_negative_cash():
    a = account()
    order = OrderDraft(
        ticker="AAPL",
        side=Side.BUY,
        quantity=Decimal("1000"),
        max_acceptable_buy_price=Decimal("200"),
        preferred_limit=Decimal("200"),
        target_weight=Decimal("1"),
        current_weight=Decimal("0"),
        estimated_notional=Decimal("200000"),
        time_in_force="DAY",
        status=RunStatus.READY_FOR_MANUAL_ENTRY,
        reason="x",
    )
    report = ProjectedPortfolioValidator().validate(a, (order,), Decimal("50000"))
    assert not report.valid


def test_mcp_service_without_provider_fails_closed():
    assert (
        DailyAnalysisService(None).run(account(), AS_OF).overall_status
        is RunStatus.BLOCKED_STALE_MARKET
    )
    assert (
        DailyAnalysisService(None).run(account("empty-zero.json"), AS_OF).overall_status
        is RunStatus.NO_CAPITAL
    )
