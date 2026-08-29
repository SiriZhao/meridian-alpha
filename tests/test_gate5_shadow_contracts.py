from datetime import UTC, datetime
from decimal import Decimal

import pytest

from meridian.challenger import FinRLXAllocatorChallenger, ModelArtifactStatus
from meridian.dislocation import (
    DislocationAssessment,
    DislocationScreen,
    DislocationStatus,
    bounded_modifier,
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


def test_dislocation_modifier_requires_resolved_certified_evidence() -> None:
    evidence = EvidenceItem(ticker="AAPL", provider="sec", source="SEC:filing", observed_at=T,
        available_at=T, evidence_type="event")
    assessment = DislocationAssessment(ticker="AAPL", status=DislocationStatus.AVAILABLE,
        stance="BULLISH", dislocation_conviction=Decimal("1"), cited_evidence_ids=(evidence.stable_id,))
    assert bounded_modifier(assessment, (evidence,)) == Decimal("0.10")
    with pytest.raises(ValueError, match="citations"):
        bounded_modifier(assessment.model_copy(update={"cited_evidence_ids": ("unknown",)}), (evidence,))