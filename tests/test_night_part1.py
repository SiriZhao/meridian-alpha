from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.candidates import CandidateSelector
from meridian.config import (
    EvidenceCompletenessPolicy,
    EvidencePacketPolicy,
    ResearchBudgetPolicy,
)
from meridian.evidence import (
    EvidenceCompletenessEvaluator,
    EvidencePacketBuilder,
    FakeFundamentalEvidenceProvider,
    FakeMacroEvidenceProvider,
    FakeMarketEvidenceProvider,
    FakeNewsEvidenceProvider,
    ProviderCapabilities,
)
from meridian.research import (
    GraphResearchSummary,
    PointInTimeStatus,
    ResearchEvidencePacket,
    ResearchStatus,
)
from meridian.schemas import EvidenceItem

AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def budget(**updates: object) -> ResearchBudgetPolicy:
    values: dict[str, object] = {
        "max_graph_tickers_per_run": 3,
        "max_parallel_graphs": 1,
        "max_graph_age_hours": 24,
        "always_review_existing_holdings": True,
        "candidate_selection_mode": "existing_then_order",
        "minimum_quant_score": Decimal("-1"),
        "existing_holding_review_policy": "always",
    }
    values.update(updates)
    return ResearchBudgetPolicy.model_validate(values)


def test_candidate_selector_prioritizes_holdings_and_surfaces_deferred() -> None:
    features = {
        ticker: {"feature_timestamp": AS_OF, "momentum": score}
        for ticker, score in {
            "AAPL": Decimal("0.9"),
            "MSFT": Decimal("0.8"),
            "NVDA": Decimal("0.1"),
            "META": Decimal("0.7"),
        }.items()
    }
    selector = CandidateSelector()
    result = selector.build(
        ("META", "NVDA", "AAPL", "MSFT"),
        features,
        AS_OF,
        existing_holdings=("NVDA",),
        policy=budget(),
    )
    assert tuple(candidate.ticker for candidate in result.candidates) == ("NVDA", "AAPL", "MSFT")
    assert result.deferred[0].ticker == "META"
    assert result.deferred[0].deferred_reason == "BUDGET_LIMIT"
    assert result.model_dump() == selector.build(
        ("META", "NVDA", "AAPL", "MSFT"),
        features,
        AS_OF,
        existing_holdings=("NVDA",),
        policy=budget(),
    ).model_dump()


def test_candidate_selector_minimum_quant_score_is_explicit() -> None:
    result = CandidateSelector().build(
        ("AAPL", "MSFT"),
        {
            "AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.5")},
            "MSFT": {"feature_timestamp": AS_OF, "momentum": Decimal("-0.5")},
        },
        AS_OF,
        policy=budget(minimum_quant_score=Decimal("0")),
    )
    assert tuple(candidate.ticker for candidate in result.candidates) == ("AAPL",)
    assert result.deferred[0].deferred_reason == "BELOW_MINIMUM_QUANT_SCORE"


def test_candidate_future_feature_is_rejected() -> None:
    with pytest.raises(ValueError, match="after as_of"):
        CandidateSelector().build(
            ("AAPL",),
            {"AAPL": {"feature_timestamp": AS_OF + timedelta(seconds=1), "momentum": 0}},
            AS_OF,
            policy=budget(),
        )


def test_offline_providers_are_synthetic_and_not_live() -> None:
    provider = FakeMarketEvidenceProvider()
    assert provider.capabilities.supports_live is False
    evidence = provider.get_evidence("AAPL", AS_OF)
    assert evidence[0].source.startswith("SYNTHETIC")
    assert evidence[0].point_in_time_status == "HISTORICAL_REPLAY_UNSAFE"


def test_packet_builder_deduplicates_bounds_and_isolates_failures() -> None:
    class FailingProvider:
        capabilities = ProviderCapabilities(
            provider_name="broken",
            supports_live=False,
            supports_historical=True,
            supports_point_in_time=False,
            requires_api_key=False,
            execution_grade=False,
            research_grade=False,
        )

        def get_evidence(self, ticker: str, as_of: datetime):
            raise RuntimeError("fixture outage")

    providers = (
        FakeMarketEvidenceProvider(),
        FakeMarketEvidenceProvider(),
        FakeFundamentalEvidenceProvider(),
        FakeNewsEvidenceProvider(),
        FakeMacroEvidenceProvider(),
        FailingProvider(),
    )
    packet = EvidencePacketBuilder(
        EvidencePacketPolicy(
            max_total_evidence_items=3,
            max_items_per_type=1,
            max_summary_characters_per_item=20,
        ),
        clock=lambda: AS_OF,
    ).gather("AAPL", AS_OF, providers)
    assert len(packet.items) == 3
    assert len({item.stable_id for item in packet.items}) == 3
    assert any("broken:PROVIDER_FAILURE" in warning for warning in packet.warnings)
    assert "EVIDENCE_BOUNDS_APPLIED" in packet.warnings
    assert all(len(item.summary or "") <= 20 for item in packet.items)


def test_future_available_evidence_is_dropped_and_empty_reason_is_explicit() -> None:
    class FutureProvider:
        capabilities = ProviderCapabilities(
            provider_name="future",
            supports_live=False,
            supports_historical=True,
            supports_point_in_time=False,
            requires_api_key=False,
            execution_grade=False,
            research_grade=False,
        )

        def get_evidence(self, ticker: str, as_of: datetime):
            return (
                EvidenceItem(
                    ticker=ticker,
                    provider="future",
                    source="future-source",
                    observed_at=as_of,
                    available_at=as_of + timedelta(seconds=1),
                    evidence_type="news",
                ),
            )

    packet = EvidencePacketBuilder(clock=lambda: AS_OF).gather(
        "AAPL", AS_OF, (FutureProvider(),)
    )
    assert packet.items == ()
    assert packet.empty_reason is not None
    assert any("EVIDENCE_AFTER_AS_OF" in warning for warning in packet.warnings)


def test_completeness_policy_returns_structured_failure() -> None:
    packet = EvidencePacketBuilder(clock=lambda: AS_OF).gather(
        "AAPL", AS_OF, (FakeMarketEvidenceProvider(),)
    )
    diagnostics = EvidenceCompletenessEvaluator(
        EvidenceCompletenessPolicy(
            minimum_total_items=2,
            minimum_distinct_sources=2,
            required_evidence_types=("news",),
            maximum_age_by_type={"market": 1},
            minimum_point_in_time_quality=Decimal("1"),
        )
    ).evaluate(packet)
    assert not diagnostics.complete
    assert set(diagnostics.violations) == {
        "minimum_total_items",
        "minimum_distinct_sources",
        "required_evidence_types",
        "minimum_point_in_time_quality",
    }


def test_graph_summary_cannot_be_available() -> None:
    with pytest.raises(ValueError, match="AVAILABLE"):
        GraphResearchSummary(
            ticker="AAPL",
            as_of=AS_OF,
            status=ResearchStatus.AVAILABLE,
            graph_rating="Hold",
            provider="deepseek",
            model="deepseek-v4-flash",
            framework_version="0.3.1",
            started_at=AS_OF,
            completed_at=AS_OF,
            point_in_time_status=PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE,
        )


def test_empty_packet_requires_reason() -> None:
    with pytest.raises(ValueError, match="explicit reason"):
        ResearchEvidencePacket(packet_id="p", ticker="AAPL", as_of=AS_OF)


def test_naive_evidence_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceItem(source="x", observed_at=datetime(2026, 8, 28), evidence_type="news")
