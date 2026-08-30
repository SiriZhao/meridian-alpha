from datetime import UTC, datetime
from decimal import Decimal

import pytest

from meridian.alpha_fusion import (
    MAX_BASE_RESEARCH_MODIFIER,
    MAX_COMBINED_RESEARCH_MODIFIER,
    combine_research_modifiers,
    research_modifier,
)
from meridian.authorization import EvidenceAuthorizationService
from meridian.evidence import ProviderCapabilities
from meridian.research import GroundedResearchSignal, GroundedResearchStatus, ResearchEvidencePacket
from meridian.schemas import AgentSignal, EvidenceItem, EvidencePointInTimeStatus

T = datetime(2026, 8, 30, tzinfo=UTC)


def certified(direction: str, conviction: Decimal):
    item = EvidenceItem(ticker="AAPL", provider="sec", source="SEC:fixture", observed_at=T, available_at=T,
        evidence_type="event", point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    packet = ResearchEvidencePacket(packet_id="certified-aapl", ticker="AAPL", as_of=T, created_at=T, items=(item,),
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    grounded = GroundedResearchSignal(ticker="AAPL", as_of=T, direction=direction, conviction=conviction,
        thesis="Fixture certified thesis.", cited_evidence_ids=(item.stable_id,), status=GroundedResearchStatus.AVAILABLE)
    capability = ProviderCapabilities(provider_name="sec", supports_historical=True, supports_point_in_time=True, research_grade=True)
    return EvidenceAuthorizationService().authorize(grounded, packet, provider_registry={"sec": capability})


def test_bullish_and_bearish_certified_research_change_alpha_in_opposite_directions() -> None:
    assert research_modifier(certified("BULLISH", Decimal("0.8"))) > 0
    assert research_modifier(certified("BEARISH", Decimal("0.8"))) < 0


def test_research_and_dislocation_share_one_combined_cap() -> None:
    base = research_modifier(certified("BULLISH", Decimal("1")))
    assert abs(base) <= MAX_BASE_RESEARCH_MODIFIER
    assert combine_research_modifiers(base, Decimal("0.10")) <= MAX_COMBINED_RESEARCH_MODIFIER
    assert combine_research_modifiers(Decimal("0.18"), Decimal("0.10")) == MAX_COMBINED_RESEARCH_MODIFIER


def test_uncertified_or_abstaining_signal_cannot_influence_alpha() -> None:
    raw = AgentSignal(ticker="AAPL", as_of=T, direction="BULLISH", conviction=Decimal("1"), thesis="raw", source="raw")
    with pytest.raises(TypeError, match="CertifiedAgentSignal"):
        research_modifier(raw)