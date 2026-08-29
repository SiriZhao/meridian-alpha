from datetime import UTC, datetime
from decimal import Decimal

import pytest

from meridian.alpha_fusion import fuse
from meridian.authorization import EvidenceAuthorizationService
from meridian.candidates import CandidateSelector
from meridian.config import ResearchBudgetPolicy
from meridian.evidence import ProviderCapabilities
from meridian.orders import ProjectedPortfolioValidator
from meridian.pipeline import (
    FakeGraphResearchProvider,
    ResearchPipelineMode,
    ResearchPipelineService,
)
from meridian.research import (
    GroundedResearchSignal,
    GroundedResearchStatus,
    ResearchEvidencePacket,
)
from meridian.schemas import (
    AccountSnapshot,
    EvidenceItem,
    EvidencePointInTimeStatus,
    OrderDraft,
    RunStatus,
    Side,
)

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


def _order(ticker: str, amount: str) -> OrderDraft:
    price = Decimal(amount)
    return OrderDraft(
        ticker=ticker,
        side=Side.BUY,
        quantity=Decimal("1"),
        max_acceptable_buy_price=price,
        preferred_limit=price,
        target_weight=Decimal("0.1"),
        current_weight=Decimal("0"),
        estimated_notional=price,
        time_in_force="DAY",
        status=RunStatus.READY_FOR_MANUAL_ENTRY,
        reason="fixture",
    )


def test_gate26_cumulative_buy_projection() -> None:
    account = AccountSnapshot(
        snapshot_id="a",
        account_alias="fixture",
        provider="fixture",
        as_of=AS_OF,
        total_equity=Decimal("1000"),
        cash=Decimal("1000"),
        sync_state="SYNCED",
        freshness_state="VERIFIED",
    )
    report = ProjectedPortfolioValidator().validate(
        account, (_order("AAPL", "600"), _order("MSFT", "600")), Decimal("1000")
    )
    assert not report.valid
    assert report.projected_cash == Decimal("-200")
    assert report.projected_holdings == {"AAPL": Decimal("1"), "MSFT": Decimal("1")}


def test_gate26_unknown_pit_is_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceItem(source="x", observed_at=AS_OF, evidence_type="news", point_in_time_status="TOTALLY_FAKE")


def test_gate26_certified_signal_is_sealed() -> None:
    from meridian.research import CertifiedAgentSignal

    with pytest.raises(ValueError):
        CertifiedAgentSignal(signal={}, packet_id="p", certificate_id="c", provider_name="x")


def test_gate26_candidate_missing_timestamp_is_deferred() -> None:
    result = CandidateSelector().build(("AAPL",), {"AAPL": {"momentum": Decimal("0.2")}}, AS_OF, policy=_budget(1))
    assert result.candidates == ()
    assert result.deferred[0].deferred_reason == "FEATURE_TIMESTAMP_UNAVAILABLE"


def test_gate26_test_mode_never_certifies() -> None:
    result = ResearchPipelineService(
        _budget(1), graph_provider=FakeGraphResearchProvider()
    ).run(
        ("AAPL",), AS_OF, {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}}, mode=ResearchPipelineMode.TEST
    )
    assert result.agent_signals == ()


def test_gate26_synthetic_capability_cannot_authorize() -> None:
    item = EvidenceItem(
        ticker="AAPL", provider="fake", source="SYNTHETIC:fake", observed_at=AS_OF,
        available_at=AS_OF, evidence_type="market", point_in_time_status=EvidencePointInTimeStatus.SYNTHETIC,
    )
    packet = ResearchEvidencePacket(
        packet_id="p", ticker="AAPL", as_of=AS_OF, items=(item,),
        point_in_time_status=EvidencePointInTimeStatus.SYNTHETIC,
    )
    grounded = GroundedResearchSignal(
        ticker="AAPL", as_of=AS_OF, direction="BULLISH", conviction=Decimal("0.5"), thesis="x",
        cited_evidence_ids=(item.stable_id,), status=GroundedResearchStatus.AVAILABLE,
    )
    capabilities = ProviderCapabilities(
        provider_name="fake", supports_live=False, supports_historical=True,
        supports_point_in_time=False, requires_api_key=False, execution_grade=False, research_grade=False,
    )
    with pytest.raises(ValueError):
        EvidenceAuthorizationService().authorize(grounded, packet, provider_capabilities=capabilities)


def _certifiable_fixture() -> tuple[GroundedResearchSignal, ResearchEvidencePacket, ProviderCapabilities]:
    item = EvidenceItem(
        ticker="AAPL",
        provider="cert-provider",
        source="cert-source",
        observed_at=AS_OF,
        available_at=AS_OF,
        evidence_type="market",
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )
    packet = ResearchEvidencePacket(
        packet_id="cert-packet",
        ticker="AAPL",
        as_of=AS_OF,
        items=(item,),
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )
    grounded = GroundedResearchSignal(
        ticker="AAPL",
        as_of=AS_OF,
        direction="BULLISH",
        conviction=Decimal("0.8"),
        thesis="certified fixture",
        cited_evidence_ids=(item.stable_id,),
    )
    capabilities = ProviderCapabilities(
        provider_name="cert-provider",
        supports_live=False,
        supports_historical=True,
        supports_point_in_time=True,
        requires_api_key=False,
        execution_grade=False,
        research_grade=True,
    )
    return grounded, packet, capabilities


def test_gate26_future_available_at_is_rejected() -> None:
    future = AS_OF.replace(hour=15, minute=30)
    item = EvidenceItem(
        ticker="AAPL",
        source="fixture",
        provider="fixture",
        observed_at=AS_OF,
        available_at=future,
        evidence_type="news",
    )
    with pytest.raises(ValueError):
        ResearchEvidencePacket(
            packet_id="future-packet",
            ticker="AAPL",
            as_of=AS_OF,
            items=(item,),
        )


def test_gate26_direct_grounding_requires_packet_identity() -> None:
    grounded, packet, _ = _certifiable_fixture()
    other = packet.model_copy(update={"ticker": "MSFT"})
    with pytest.raises(ValueError, match="identity"):
        grounded.to_agent_signal(other)


def test_gate26_provider_capability_mismatch_fails_closed() -> None:
    grounded, packet, capabilities = _certifiable_fixture()
    mismatched = capabilities.model_copy(update={"provider_name": "other"})
    with pytest.raises(ValueError, match="provider"):
        EvidenceAuthorizationService().authorize(
            grounded, packet, provider_capabilities=mismatched
        )


def test_gate26_live_capable_provider_is_rejected_in_test_mode() -> None:
    class NetworkProvider(FakeGraphResearchProvider):
        network_capable = True

    graph = NetworkProvider()
    result = ResearchPipelineService(_budget(1), graph_provider=graph).run(
        ("AAPL",),
        AS_OF,
        {"AAPL": {"feature_timestamp": AS_OF, "momentum": Decimal("0.2")}},
        mode=ResearchPipelineMode.TEST,
    )
    assert result.agent_signals == ()
    assert graph.calls == []
    assert "NETWORK_PROVIDER_FORBIDDEN_IN_OFFLINE_MODE" in result.warnings


def test_gate26_alpha_fusion_regime_influence_is_bounded() -> None:
    grounded, packet, capabilities = _certifiable_fixture()
    certified = EvidenceAuthorizationService().authorize(
        grounded, packet, provider_capabilities=capabilities
    )
    bounded = fuse(certified, Decimal("0"), regime_multiplier=Decimal("1"))
    oversized = fuse(certified, Decimal("0"), regime_multiplier=Decimal("100"))
    assert oversized.score == bounded.score
