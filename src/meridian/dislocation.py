"""Bounded large-cap dislocation research contracts; shadow-only."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import Field

from meridian.research import CertifiedEvidenceView
from meridian.schemas import StableModel


class DislocationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    ABSTAIN = "ABSTAIN"
    INSUFFICIENT_GROUNDING = "INSUFFICIENT_GROUNDING"


class DislocationCandidate(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    drawdown: Decimal = Field(ge=-1, le=0)
    momentum_reversal: Decimal = Field(ge=-1, le=1)
    realized_volatility: Decimal = Field(ge=0, le=10)
    quant_alpha: Decimal = Field(ge=-1, le=1)
    reasons: tuple[str, ...]


class DislocationAssessment(StableModel):
    ticker: str
    status: DislocationStatus
    stance: str | None = Field(default=None, pattern=r"^(BULLISH|BEARISH|NEUTRAL)$")
    dislocation_conviction: Decimal | None = Field(default=None, ge=0, le=1)
    horizon: str | None = None
    core_thesis: str | None = None
    what_market_may_be_pricing: str | None = None
    why_it_may_be_wrong: str | None = None
    catalysts: tuple[str, ...] = ()
    structural_risks: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    cited_evidence_ids: tuple[str, ...] = ()


class DislocationScreen:
    """Deterministic bounded pre-screen; it does not call an LLM."""

    def select(
        self, features: dict[str, dict[str, Decimal]], *, limit: int = 3
    ) -> tuple[DislocationCandidate, ...]:
        candidates: list[DislocationCandidate] = []
        for ticker, values in sorted(features.items()):
            drawdown = values.get("drawdown", Decimal("0"))
            reversal = values.get("momentum_reversal", Decimal("0"))
            if drawdown > Decimal("-0.10") or reversal <= 0:
                continue
            candidates.append(
                DislocationCandidate(
                    ticker=ticker,
                    drawdown=drawdown,
                    momentum_reversal=reversal,
                    realized_volatility=values.get("realized_volatility", Decimal("0")),
                    quant_alpha=values.get("quant_alpha", Decimal("0")),
                    reasons=("DRAWDOWN_THRESHOLD", "MOMENTUM_REVERSAL"),
                )
            )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (item.drawdown, -item.momentum_reversal, item.ticker),
            )[:limit]
        )


_CERTIFIED_DISLOCATION_TOKEN = object()


class CertifiedDislocationAssessment(StableModel):
    """Sealed assessment constructed only from an exact CertifiedEvidenceView."""

    assessment: DislocationAssessment
    evidence_view_packet_id: str

    def __init__(self, **data: Any) -> None:
        if data.pop("_certification_token", None) is not _CERTIFIED_DISLOCATION_TOKEN:
            raise ValueError("CertifiedDislocationAssessment requires CertifiedEvidenceView certification")
        super().__init__(**data)


def certify_dislocation_assessment(
    assessment: DislocationAssessment, view: CertifiedEvidenceView
) -> CertifiedDislocationAssessment:
    packet = view.packet
    if assessment.ticker != packet.ticker:
        raise ValueError("dislocation assessment ticker does not match CertifiedEvidenceView")
    allowed = {item.stable_id for item in packet.items}
    if assessment.status is DislocationStatus.AVAILABLE:
        if not assessment.cited_evidence_ids or not set(assessment.cited_evidence_ids).issubset(allowed):
            raise ValueError("dislocation citations must resolve to exact CertifiedEvidenceView")
    return CertifiedDislocationAssessment(
        _certification_token=_CERTIFIED_DISLOCATION_TOKEN,
        assessment=assessment,
        evidence_view_packet_id=packet.packet_id,
    )


def bounded_modifier(
    certified: CertifiedDislocationAssessment, *, maximum: Decimal = Decimal("0.10")
) -> Decimal:
    """Return only a bounded modifier from sealed certified evidence research."""
    if not isinstance(certified, CertifiedDislocationAssessment):
        raise TypeError("bounded dislocation modifier requires CertifiedDislocationAssessment")
    assessment = certified.assessment
    if assessment.status is not DislocationStatus.AVAILABLE or assessment.dislocation_conviction is None:
        return Decimal("0")
    sign = {
        "BULLISH": Decimal("1"),
        "BEARISH": Decimal("-1"),
        "NEUTRAL": Decimal("0"),
    }.get(assessment.stance or "NEUTRAL", Decimal("0"))
    return max(-maximum, min(maximum, sign * assessment.dislocation_conviction * maximum))