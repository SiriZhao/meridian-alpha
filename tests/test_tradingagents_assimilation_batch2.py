from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from meridian.audit import AuditStore
from meridian.daily_research import ResearchFailureStatus
from meridian.data.models import DataCategory, EvidenceRecord, ResearchDataRequirement, SourceType
from meridian.data.retrieval_orchestrator import EvidenceCache, RetrievalOrchestrator
from meridian.fundamentals import SECCompanyFactsNumericProvider
from meridian.paper import DEFAULT_ACCOUNT, PaperLedger, PaperSettings
from meridian.price_proposal import GroundedPriceProposal, PriceProposalPolicy, PriceProposalStatus
from meridian.research_backtest import (
    HistoricalDecision,
    HistoricalOutcome,
    ResearchBacktestRunner,
    date_grid,
)

T = datetime(2026, 9, 18, 16, tzinfo=UTC)


def req() -> ResearchDataRequirement:
    return ResearchDataRequirement(
        symbol="AAPL",
        asset_type="EQUITY",
        field="news",
        category=DataCategory.NEWS,
        reason="test",
        freshness_requirement="1d",
    )


def ev(requirement, as_of, *, timestamp=None, available_at=None, provider="fixture"):
    return EvidenceRecord(
        requirement_key=requirement.key,
        field=requirement.field,
        category=requirement.category,
        value="fact",
        unit="TEXT",
        symbol=requirement.symbol,
        timestamp=timestamp or as_of,
        as_of=as_of,
        available_at=available_at,
        source="fixture",
        source_type=SourceType.OFFICIAL_PRIMARY,
        retrieved_at=T,
        provider=provider,
        confidence=Decimal("1"),
        raw_reference="fixture",
        expires_at=T + timedelta(days=30),
    )


def test_news_future_availability_is_rejected():
    with pytest.raises(ValidationError, match="AVAILABLE_AT_AFTER_AS_OF"):
        ev(req(), T, available_at=T + timedelta(seconds=1))


def test_cache_isolated_by_temporal_identity(tmp_path):
    cache = EvidenceCache(tmp_path, clock=lambda: T)
    requirement = req()
    cache.store(requirement, (ev(requirement, T),), as_of=T)
    assert cache.load(requirement, as_of=T)
    assert cache.load(requirement, as_of=T - timedelta(days=1)) == ()
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_fallback_rejects_mismatched_future_context():
    requirement = req()

    class Provider:
        def __init__(self, name, future):
            self.provider_name, self.future = name, future

        def supports(self, requirement: ResearchDataRequirement) -> bool:
            return True

        def retrieve(
            self, requirement: ResearchDataRequirement, *, as_of: datetime
        ) -> tuple[EvidenceRecord, ...]:
            item_as_of = as_of + timedelta(days=1) if self.future else as_of
            return (
                ev(
                    requirement,
                    item_as_of,
                    timestamp=as_of,
                    provider=self.provider_name,
                ),
            )

    package = RetrievalOrchestrator(
        (Provider("future", True), Provider("safe", False)), max_retries=0, clock=lambda: T
    ).retrieve((requirement,), as_of=T)
    assert package.evidence[0].provider == "safe"
    failure = package.provider_results[0].failure
    assert failure is not None and failure.reason == "PROVIDER_INVALID_RESPONSE"


def test_sec_transport_retries_and_does_not_report_no_fundamentals(tmp_path):
    calls = []

    class Response:
        def read(self):
            return json.dumps({"cik": 320193, "facts": {}}).encode()

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise TimeoutError
        return Response()

    resolver = type(
        "Resolver", (), {"resolve": lambda self, ticker: ("0000320193", "Apple", None, T)}
    )()
    provider = SECCompanyFactsNumericProvider(
        opener=opener,
        resolver=resolver,
        clock=lambda: T,
        max_retries=1,
        sleeper=lambda _: None,
        cache_directory=tmp_path,
    )
    assert provider.get_observations("AAPL") == ()
    assert len(calls) == 2 and provider.last_transport_status == "NETWORK"

    unavailable = SECCompanyFactsNumericProvider(
        opener=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()),
        resolver=resolver,
        clock=lambda: T,
        max_retries=0,
    )
    with pytest.raises(ValueError, match="SEC_COMPANYFACTS_UNAVAILABLE"):
        unavailable.get_observations("AAPL")


def test_paper_ledger_exports_immutable_research_snapshot(tmp_path):
    ledger = PaperLedger(AuditStore(tmp_path / "paper.sqlite3"), PaperSettings())
    ledger.initialize(DEFAULT_ACCOUNT, cash=Decimal("1000"), now=T)
    snapshot = ledger.research_portfolio_snapshot(DEFAULT_ACCOUNT, observed_at=T)
    assert snapshot.cash == snapshot.equity == Decimal("1000")
    assert snapshot.positions == () and snapshot.concentration == 0
    with pytest.raises(ValidationError):
        snapshot.cash = Decimal("0")
    assert not hasattr(snapshot, "apply_fill")


def test_price_proposal_staleness_is_policy_owned():
    proposal = GroundedPriceProposal(
        symbol="AAPL",
        reference_price=Decimal("100"),
        entry_zone=(Decimal("99"), Decimal("101")),
        stop=Decimal("95"),
        target=Decimal("110"),
        market_timestamp=T,
        evidence_ids=("quote-1",),
        generated_at=T,
        valid_until=T + timedelta(hours=1),
    )
    assert (
        proposal.status_at(T + timedelta(seconds=30), PriceProposalPolicy(maximum_age_seconds=60))
        is PriceProposalStatus.VALID
    )
    assert (
        proposal.status_at(T + timedelta(seconds=61), PriceProposalPolicy(maximum_age_seconds=60))
        is PriceProposalStatus.PRICE_PROPOSAL_STALE
    )


def test_backtest_grid_resume_and_store_are_isolated(tmp_path):
    calls = []

    def evaluate(symbol, context):
        calls.append((symbol, context.trading_date))
        return HistoricalDecision(
            symbol=symbol,
            direction="BULLISH",
            confidence=Decimal("0.8"),
            decision_status=ResearchFailureStatus.VALID,
            research_status="READY",
            evidence_ids=("e1",),
            evidence_coverage=Decimal("1"),
        )

    runner = ResearchBacktestRunner(
        tmp_path,
        evaluate,
        lambda symbol, day, holding: HistoricalOutcome(forward_return=Decimal("0.05")),
    )
    dates = date_grid(date(2026, 9, 15), date(2026, 9, 16))
    first = runner.run(run_id="r1", symbols=("AAPL", "MSFT"), dates=dates, holding_period_days=5)
    second = runner.run(run_id="r1", symbols=("AAPL", "MSFT"), dates=dates, holding_period_days=5)
    assert first["cells_run"] == 4 and second["cells_run"] == 0
    assert len(calls) == 4 and first["directional_accuracy"] == 1.0
    assert (tmp_path / "backtests" / "r1" / "decision_log.jsonl").is_file()
    assert not list(tmp_path.rglob("*.sqlite3"))
