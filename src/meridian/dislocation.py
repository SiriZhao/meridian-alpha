"""Bounded large-cap dislocation research contracts; shadow-only."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from meridian.schemas import EvidenceItem, StableModel


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


def bounded_modifier(
    assessment: DislocationAssessment,
    evidence: tuple[EvidenceItem, ...],
    *,
    maximum: Decimal = Decimal("0.10"),
) -> Decimal:
    if assessment.status is not DislocationStatus.AVAILABLE or assessment.dislocation_conviction is None:
        return Decimal("0")
    allowed = {item.stable_id for item in evidence}
    if not assessment.cited_evidence_ids or not set(assessment.cited_evidence_ids).issubset(allowed):
        raise ValueError("dislocation citations must resolve to certified evidence")
    sign = {
        "BULLISH": Decimal("1"),
        "BEARISH": Decimal("-1"),
        "NEUTRAL": Decimal("0"),
    }.get(assessment.stance or "NEUTRAL", Decimal("0"))
    return max(-maximum, min(maximum, sign * assessment.dislocation_conviction * maximum))