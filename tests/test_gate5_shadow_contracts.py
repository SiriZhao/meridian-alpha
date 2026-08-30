from datetime import UTC, datetime
from decimal import Decimal

import pytest

from meridian.challenger import FinRLXAllocatorChallenger, ModelArtifactStatus
from meridian.dislocation import (
    DislocationAssessment,
    DislocationScreen,
    DislocationStatus,
    bounded_modifier,
    certify_dislocation_assessment,
)
from meridian.schemas import AccountSnapshot, AccountSyncState, EvidenceItem, FreshnessState

T = datetime(2026, 8, 30, tzinfo=UTC)


def account() -> AccountSnapshot:
    return AccountSnapshot(snapshot_id="synthetic", account_alias="fixture", provider="fixture", as_of=T,
        total_equity=Decimal("50000"), cash=Decimal("50000"), sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED)


def test_finrlx_challenger_requires_manifest_and_never_promotes() -> None:
    result = FinRLXAllocatorChallenger().compare(account(), "a" * 64, None)
    assert result.status is ModelArtifactStatus.MODEL_UNAVAILABLE
    assert result.promotion_eligible is False


def test_dislocation_screen_is_bounded_and_deterministic() -> None:
    selected = DislocationScreen().select({
        "AAPL": {"drawdown": Decimal("-0.20"), "momentum_reversal": Decimal("0.2")},
        "MSFT": {"drawdown": Decimal("-0.05"), "momentum_reversal": Decimal("0.9")},
        "NVDA": {"drawdown": Decimal("-0.30"), "momentum_reversal": Decimal("0.1")},
    })
    assert tuple(item.ticker for item in selected) == ("NVDA", "AAPL")


def test_dislocation_modifier_requires_sealed_certified_evidence_view() -> None:
    from meridian.evidence import ProviderCapabilities
    from meridian.research import CertifiedEvidenceView, ResearchContextPacket
    from meridian.schemas import EvidencePointInTimeStatus

    evidence = EvidenceItem(ticker="AAPL", provider="sec", source="SEC:filing", observed_at=T,
        available_at=T, evidence_type="event", point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    assessment = DislocationAssessment(ticker="AAPL", status=DislocationStatus.AVAILABLE,
        stance="BULLISH", dislocation_conviction=Decimal("1"), cited_evidence_ids=(evidence.stable_id,))
    view = CertifiedEvidenceView.from_context(ResearchContextPacket(context_id="c", ticker="AAPL", as_of=T,
        created_at=T, items=(evidence,)), provider_registry={"sec": ProviderCapabilities(provider_name="sec",
        supports_historical=True, supports_point_in_time=True, research_grade=True)}, clock=lambda: T)
    certified = certify_dislocation_assessment(assessment, view)
    assert bounded_modifier(certified) == Decimal("0.10")
    with pytest.raises(ValueError, match="exact CertifiedEvidenceView"):
        certify_dislocation_assessment(assessment.model_copy(update={"cited_evidence_ids": ("unknown",)}), view)

def test_raw_dislocation_assessment_cannot_authorize_modifier() -> None:
    raw = DislocationAssessment(ticker="AAPL", status=DislocationStatus.AVAILABLE,
        stance="BULLISH", dislocation_conviction=Decimal("1"), cited_evidence_ids=("not-enough",))
    with pytest.raises(TypeError, match="CertifiedDislocationAssessment"):
        bounded_modifier(raw)  # type: ignore[arg-type]