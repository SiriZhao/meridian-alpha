from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from meridian.candidates import CandidateSelector
from meridian.config import EvidencePacketPolicy, ResearchBudgetPolicy, load_policies
from meridian.evidence import (
    EvidencePacketBuilder,
    EvidenceProvider,
    FakeFundamentalEvidenceProvider,
    FakeMacroEvidenceProvider,
    FakeMarketEvidenceProvider,
    FakeNewsEvidenceProvider,
)
from meridian.orchestrator import DailyOrchestrator
from meridian.pipeline import (
    FakeGraphResearchProvider,
    ResearchPipelineMode,
    ResearchPipelineService,
    ResearchPipelineStatus,
)
from meridian.research import (
    FakeGroundedResearchNormalizer,
    GroundedResearchSignal,
    GroundedResearchStatus,
)
from meridian.schemas import AccountSnapshot, RunStatus

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def _budget(limit: int = 3) -> ResearchBudgetPolicy:
    return ResearchBudgetPolicy(
        max_graph_tickers_per_run=limit,
        max_parallel_graphs=1,
        max_graph_age_hours=24,
        always_review_existing_holdings=True,
        candidate_selection_mode="existing_then_order",
        minimum_quant_score=Decimal("-1"),
        existing_holding_review_policy="always",
    )


def _pipeline(
    *,
    budget: ResearchBudgetPolicy,
    normalizer: FakeGroundedResearchNormalizer | None = None,
    providers: tuple[EvidenceProvider, ...] = (),
) -> tuple[ResearchPipelineService, FakeGraphResearchProvider]:
    graph = FakeGraphResearchProvider()
    service = ResearchPipelineService(
        budget,
        graph_provider=graph,
        evidence_builder=EvidencePacketBuilder(
            EvidencePacketPolicy(
                max_total_evidence_items=20,
                max_items_per_type=5,
                max_summary_characters_per_item=500,
            ),
            clock=lambda: AS_OF,
        ),
        evidence_providers=providers,
        normalizer=normalizer,
    )
    return service, graph


def test_scenario_a_zero_capital_stops_before_research_and_market() -> None:
    account = AccountSnapshot.model_validate_json(
        (ROOT / "schemas" / "examples" / "empty-zero.json").read_text(encoding="utf-8")
    )

    class NoCallMarket:
        provider_name = "no-call"

        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"zero capital must not call market method {name}")

    class NoCallResearch:
        def analyze(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("zero capital must not invoke research")

    result = DailyOrchestrator(
        load_policies(ROOT / "policies"), NoCallMarket(), NoCallResearch()  # type: ignore[arg-type]
    ).run(account, AS_OF)
    assert result.overall_status is RunStatus.NO_CAPITAL
    assert result.orders == ()


def test_scenario_b_synthetic_pipeline_reaches_grounded_signal_and_fusion() -> None:
    providers = (
        FakeMarketEvidenceProvider(),
        FakeFundamentalEvidenceProvider(),
        FakeNewsEvidenceProvider(),
        FakeMacroEvidenceProvider(),
    )
    builder = EvidencePacketBuilder(clock=lambda: AS_OF)
    item_id = builder.gather("AAPL", AS_OF, providers).items[0].stable_id
    signal = GroundedResearchSignal(
        ticker="AAPL",
        as_of=AS_OF,
        direction="BULLISH",
        conviction=Decimal("0.65"),
        thesis="Synthetic grounding only; not live research.",
        risks=("Synthetic fixture",),
        cited_evidence_ids=(item_id,),
    )
    service, graph = _pipeline(
        budget=_budget(1),
        providers=providers,
        normalizer=FakeGroundedResearchNormalizer({"AAPL": signal}, allow_synthetic=True),
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.4")}},
        mode=ResearchPipelineMode.TEST,
    )
    # Synthetic TEST artifacts remain diagnostic-only and cannot cross the
    # executable certification boundary.
    assert result.status is ResearchPipelineStatus.INSUFFICIENT_GROUNDING
    assert result.synthetic is True
    assert graph.calls == ["AAPL"]
    assert result.agent_signals == ()


def test_scenario_c_existing_holding_is_prioritized_and_deferred_is_explicit() -> None:
    service, graph = _pipeline(budget=_budget(3))
    tickers = ("AAPL", "MSFT", "NVDA", "META", "GOOGL")
    features = {
        ticker: {"feature_timestamp": AS_OF, "momentum": Decimal(index) / Decimal("10")}
        for index, ticker in enumerate(tickers, start=1)
    }
    result = service.run(
        tickers,
        AS_OF,
        features,
        existing_holdings=("GOOGL",),
        mode=ResearchPipelineMode.TEST,
    )
    assert result.candidate_set.candidates[0].ticker == "GOOGL"
    assert len(result.candidate_set.candidates) == 3
    assert len(graph.calls) == 3
    assert {candidate.ticker for candidate in result.candidate_set.deferred} == {"AAPL", "MSFT"}
    assert all(candidate.deferred_reason for candidate in result.candidate_set.deferred)


def test_scenario_d_graph_success_with_insufficient_evidence_is_not_available() -> None:
    service, _ = _pipeline(
        budget=_budget(1),
        providers=(FakeMarketEvidenceProvider(),),
        normalizer=FakeGroundedResearchNormalizer(),
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.3")}},
        mode=ResearchPipelineMode.TEST,
    )
    assert result.graph_summaries[0].graph_rating == "Hold"
    assert result.grounded_outcomes[0].status is GroundedResearchStatus.INSUFFICIENT_GROUNDING
    assert result.agent_signals == ()
    assert result.status is ResearchPipelineStatus.INSUFFICIENT_GROUNDING


def test_scenario_e_unknown_evidence_citation_fails_closed() -> None:
    service, _ = _pipeline(
        budget=_budget(1),
        providers=(FakeMarketEvidenceProvider(),),
        normalizer=FakeGroundedResearchNormalizer(
            {
                "AAPL": {
                    "ticker": "AAPL",
                    "as_of": AS_OF,
                    "direction": "BULLISH",
                    "conviction": Decimal("0.6"),
                    "thesis": "Synthetic invalid citation.",
                    "cited_evidence_ids": ("does-not-exist",),
                    "status": GroundedResearchStatus.AVAILABLE,
                }
            },
            allow_synthetic=True,
        ),
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.3")}},
        mode=ResearchPipelineMode.TEST,
    )
    assert result.grounded_outcomes[0].status is GroundedResearchStatus.INVALID_OUTPUT
    assert result.agent_signals == ()


def test_candidate_selector_is_deterministic_for_equal_scores() -> None:
    features = {
        ticker: {"feature_timestamp": AS_OF, "momentum": Decimal("0.1")}
        for ticker in ("MSFT", "AAPL", "NVDA")
    }
    result = CandidateSelector().build(
        ("NVDA", "MSFT", "AAPL"), features, AS_OF, policy=_budget(3)
    )
    assert tuple(candidate.ticker for candidate in result.candidates) == ("AAPL", "MSFT", "NVDA")
