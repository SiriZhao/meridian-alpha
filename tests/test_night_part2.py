from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.config import EvidencePacketPolicy, ResearchBudgetPolicy, load_policies
from meridian.evidence import (
    EvidencePacketBuilder,
    FakeMarketEvidenceProvider,
    ProviderCapabilities,
)
from meridian.pipeline import (
    FakeGraphResearchProvider,
    ResearchPipelineMode,
    ResearchPipelineService,
    ResearchPipelineStatus,
)
from meridian.research import (
    DeepSeekGroundedResearchNormalizer,
    EvidenceCitationValidator,
    FakeGroundedResearchNormalizer,
    GraphResearchSummary,
    GroundedResearchReplayStore,
    GroundedResearchSignal,
    GroundedResearchStatus,
    PointInTimeStatus,
    ResearchEvidencePacket,
    ResearchStatus,
)
from meridian.schemas import EvidenceItem

AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def budget(max_graph_tickers_per_run: int = 3) -> ResearchBudgetPolicy:
    return ResearchBudgetPolicy(
        max_graph_tickers_per_run=max_graph_tickers_per_run,
        max_parallel_graphs=1,
        max_graph_age_hours=24,
        always_review_existing_holdings=True,
        candidate_selection_mode="existing_then_order",
        minimum_quant_score=Decimal("-1"),
        existing_holding_review_policy="always",
    )


def summary(ticker: str = "AAPL") -> GraphResearchSummary:
    return GraphResearchSummary(
        ticker=ticker,
        as_of=AS_OF,
        status=ResearchStatus.GRAPH_SUMMARY_ONLY,
        graph_rating="Buy",
        selected_analysts=("market",),
        reports_present=("market_report",),
        provider="synthetic-graph",
        model="synthetic-v1",
        framework_version="0.3.1",
        started_at=AS_OF,
        completed_at=AS_OF,
        point_in_time_status=PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE,
    )


def packet(*, status: str = "VERIFIED") -> ResearchEvidencePacket:
    item = EvidenceItem(
        ticker="AAPL",
        provider="fixture-provider",
        source="fixture-source",
        observed_at=AS_OF,
        available_at=AS_OF,
        evidence_type="market",
        point_in_time_status=status,
    )
    return ResearchEvidencePacket(
        packet_id="packet-aapl",
        ticker="AAPL",
        as_of=AS_OF,
        created_at=AS_OF,
        items=(item,),
        point_in_time_status=status,
    )


def grounded_signal(evidence_id: str, **updates: object) -> GroundedResearchSignal:
    values: dict[str, object] = {
        "ticker": "AAPL",
        "as_of": AS_OF,
        "direction": "BULLISH",
        "conviction": Decimal("0.7"),
        "thesis": "Explicitly grounded fixture thesis.",
        "risks": ("fixture risk",),
        "cited_evidence_ids": (evidence_id,),
        "graph_rating": "Buy",
        "status": GroundedResearchStatus.AVAILABLE,
    }
    values.update(updates)
    return GroundedResearchSignal.model_validate(values)


def test_unknown_citation_is_invalid_output() -> None:
    result = FakeGroundedResearchNormalizer(
        {"AAPL": grounded_signal("missing-id")},
        allow_synthetic=False,
    ).normalize(summary(), packet(), AS_OF)
    assert result.status is GroundedResearchStatus.INVALID_OUTPUT
    assert result.signal is None


def test_missing_citation_is_rejected_when_required() -> None:
    with pytest.raises(ValueError, match="requires evidence citations"):
        grounded_signal("unused", cited_evidence_ids=())


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("1.01")])
def test_grounded_conviction_is_bounded(value: Decimal) -> None:
    with pytest.raises(ValueError):
        grounded_signal("unused", conviction=value)


def test_valid_grounded_signal_becomes_agent_signal_only_after_citation_gate() -> None:
    item = packet().items[0]
    signal = grounded_signal(item.stable_id)
    agent = signal.to_agent_signal(packet())
    assert agent.ticker == "AAPL"
    assert agent.conviction == Decimal("0.7")
    assert agent.evidence == (item,)


def test_graph_rating_does_not_create_conviction() -> None:
    result = FakeGroundedResearchNormalizer().normalize(summary(), packet(), AS_OF)
    assert result.status is GroundedResearchStatus.INSUFFICIENT_GROUNDING
    assert result.signal is None


def test_live_disabled_prevents_graph_invocation() -> None:
    graph = FakeGraphResearchProvider()
    service = ResearchPipelineService(
        budget(),
        graph_provider=graph,
        live_enabled=False,
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}},
        mode=ResearchPipelineMode.LIVE,
    )
    assert result.status is ResearchPipelineStatus.LIVE_RESEARCH_DISABLED
    assert graph.calls == []


def test_graph_summary_alone_is_not_available() -> None:
    service = ResearchPipelineService(
        budget(),
        graph_provider=FakeGraphResearchProvider(),
        evidence_providers=(FakeMarketEvidenceProvider(),),
        normalizer=FakeGroundedResearchNormalizer(),
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}},
    )
    assert result.status is ResearchPipelineStatus.INSUFFICIENT_GROUNDING
    assert result.agent_signals == ()
    assert result.grounded_outcomes[0].status is GroundedResearchStatus.INSUFFICIENT_GROUNDING


def test_valid_grounded_result_produces_agent_signal() -> None:
    evidence_packet = packet()
    item_id = evidence_packet.items[0].stable_id

    class FixtureProvider:
        capabilities = ProviderCapabilities(
            provider_name="fixture-provider",
            supports_live=False,
            supports_historical=True,
            supports_point_in_time=True,
            requires_api_key=False,
            execution_grade=False,
            research_grade=True,
        )

        def get_evidence(self, ticker: str, as_of: datetime):
            return evidence_packet.items

    service = ResearchPipelineService(
        budget(),
        graph_provider=FakeGraphResearchProvider(),
        evidence_builder=EvidencePacketBuilder(
            EvidencePacketPolicy(
                max_total_evidence_items=5,
                max_items_per_type=5,
                max_summary_characters_per_item=100,
            ),
            clock=lambda: AS_OF,
        ),
        evidence_providers=(FixtureProvider(),),
        normalizer=FakeGroundedResearchNormalizer(
            {"AAPL": grounded_signal(item_id)},
            allow_synthetic=False,
        ),
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}},
    )
    # TEST mode preserves the grounded result for diagnostics but never
    # issues an executable certificate.
    assert result.status is ResearchPipelineStatus.INSUFFICIENT_GROUNDING
    assert result.agent_signals == ()
    assert result.grounded_outcomes[0].status is GroundedResearchStatus.AVAILABLE


def test_provider_failure_is_isolated() -> None:
    class BrokenProvider:
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
            raise RuntimeError("offline fixture failure")

    service = ResearchPipelineService(
        budget(),
        graph_provider=FakeGraphResearchProvider(),
        evidence_providers=(BrokenProvider(),),
        normalizer=FakeGroundedResearchNormalizer(),
    )
    result = service.run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}},
    )
    assert result.status is ResearchPipelineStatus.INSUFFICIENT_GROUNDING
    assert result.evidence_packets[0].provider_statuses == ("broken:FAILED:0",)


def test_budget_limits_graph_calls_before_invocation() -> None:
    tickers = tuple(f"TICK{i:03d}" for i in range(100))
    features = {
        ticker: {"feature_timestamp": AS_OF, "momentum": Decimal("0.1")}
        for ticker in tickers
    }
    graph = FakeGraphResearchProvider()
    result = ResearchPipelineService(
        budget(3),
        graph_provider=graph,
        normalizer=FakeGroundedResearchNormalizer(),
    ).run(tickers, AS_OF, features)
    assert len(result.candidate_set.candidates) == 3
    assert len(graph.calls) == 3
    assert len(result.candidate_set.deferred) == 97


def test_replay_store_round_trip_and_hash_validation(tmp_path: Path) -> None:
    store = GroundedResearchReplayStore(tmp_path)
    saved_graph = store.record_graph(summary())
    saved_packet = store.record_packet(packet())
    saved_signal = store.record_signal(grounded_signal(packet().items[0].stable_id))
    assert store.load_graph("AAPL", AS_OF) == summary()
    assert store.load_packet("AAPL", AS_OF) == packet()
    assert store.load_signal("AAPL", AS_OF).conviction == Decimal("0.7")
    assert saved_graph.is_file() and saved_packet.is_file() and saved_signal.is_file()
    payload = json.loads(saved_signal.read_text(encoding="utf-8"))
    payload["content_hash"] = "tampered"
    saved_signal.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        store.load_signal("AAPL", AS_OF)


def test_replay_mode_never_calls_graph_provider(tmp_path: Path) -> None:
    store = GroundedResearchReplayStore(tmp_path)
    store.record_graph(summary())
    store.record_packet(packet())
    store.record_signal(grounded_signal(packet().items[0].stable_id))
    graph = FakeGraphResearchProvider()
    result = ResearchPipelineService(
        budget(),
        graph_provider=graph,
        replay_store=store,
    ).run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}},
        mode=ResearchPipelineMode.REPLAY,
    )
    assert graph.calls == []
    assert result.grounded_outcomes[0].status is GroundedResearchStatus.AVAILABLE
    assert result.status is ResearchPipelineStatus.HISTORICAL_REPLAY_UNSAFE


def test_deepseek_normalizer_disabled_without_client_call() -> None:
    policies = load_policies(Path(__file__).parents[1] / "policies")
    settings = policies.models.research
    assert settings is not None
    called = []

    def forbidden_client(*args: object, **kwargs: object):
        called.append(True)
        raise AssertionError("disabled normalizer must not create a client")

    result = DeepSeekGroundedResearchNormalizer(
        settings.model_copy(update={"live_enabled": False}),
        client_factory=forbidden_client,
    ).normalize(summary(), packet(), AS_OF)
    assert result.status is GroundedResearchStatus.LIVE_RESEARCH_DISABLED
    assert called == []


def test_future_citation_is_rejected() -> None:
    future = packet().items[0].model_copy(update={"available_at": AS_OF + timedelta(seconds=1)})
    future_packet = packet().model_copy(update={"items": (future,)})
    with pytest.raises(ValueError, match="after as_of"):
        EvidenceCitationValidator().validate(future_packet, (future.stable_id,), AS_OF)
