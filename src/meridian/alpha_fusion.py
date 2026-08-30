"""Deterministic fusion of certified research and quant features."""

from __future__ import annotations

from decimal import Decimal

from meridian.authorization import CertifiedAgentSignal
from meridian.research import ResearchOutcome
from meridian.schemas import AgentSignal, AlphaScore

_DIRECTION = {"BULLISH": Decimal("1"), "BEARISH": Decimal("-1"), "NEUTRAL": Decimal("0")}

# A single combined budget prevents ordinary research and dislocation research
# from independently spending a full alpha allowance on the same evidence.
MAX_BASE_RESEARCH_MODIFIER = Decimal("0.18")
MAX_DISLOCATION_MODIFIER = Decimal("0.10")
MAX_COMBINED_RESEARCH_MODIFIER = Decimal("0.20")


def research_modifier(
    certified: CertifiedAgentSignal | AgentSignal,
    *,
    regime_multiplier: Decimal = Decimal("1"),
    maximum: Decimal = MAX_BASE_RESEARCH_MODIFIER,
) -> Decimal:
    """Return the bounded base research contribution from an authorized signal."""
    signal = certified.signal if isinstance(certified, CertifiedAgentSignal) else None
    if signal is None:
        raise TypeError("Alpha Fusion requires CertifiedAgentSignal")
    components = [signal.fundamental_score, signal.sentiment_score, signal.news_score]
    present = [value for value in components if value is not None]
    qualitative = sum(present, Decimal("0")) / Decimal(len(present)) if present else _DIRECTION[signal.direction]
    evidence_quality = min(Decimal("1"), Decimal(len(signal.evidence)) / Decimal("3")) if signal.evidence else Decimal("0")
    bounded_regime = max(Decimal("0"), min(Decimal("1"), regime_multiplier))
    raw = Decimal("0.55") * qualitative * signal.conviction * evidence_quality * bounded_regime
    return max(-maximum, min(maximum, raw))


def combine_research_modifiers(
    base: Decimal,
    dislocation: Decimal,
    *,
    maximum: Decimal = MAX_COMBINED_RESEARCH_MODIFIER,
) -> Decimal:
    """Apply an incremental dislocation contribution under one combined cap."""
    return max(-maximum, min(maximum, base + dislocation))


def fuse(
    certified: CertifiedAgentSignal | AgentSignal,
    technical_score: Decimal,
    regime_multiplier: Decimal = Decimal("1"),
    valuation_score: Decimal | None = None,
) -> AlphaScore:
    """Fuse only a certified signal; plain AgentSignal input is rejected."""
    signal = certified.signal if isinstance(certified, CertifiedAgentSignal) else None
    if signal is None:
        raise TypeError("Alpha Fusion requires CertifiedAgentSignal")
    _ = valuation_score  # valuation has no independent path outside certified signal evidence.
    quant_component = Decimal("0.45") * max(Decimal("-1"), min(Decimal("1"), technical_score))
    evidence_quality = min(Decimal("1"), Decimal(len(signal.evidence)) / Decimal("3")) if signal.evidence else Decimal("0")
    research_component = research_modifier(certified, regime_multiplier=regime_multiplier)
    risk_penalty = signal.risk_score if signal.risk_score is not None else Decimal("0")
    score = max(Decimal("-1"), min(Decimal("1"), quant_component + research_component - risk_penalty))
    direction = "BULLISH" if score > 0 else "BEARISH" if score < 0 else "NEUTRAL"
    return AlphaScore(
        ticker=signal.ticker,
        score=score,
        confidence=signal.conviction,
        expected_direction=direction,
        risk_penalty=risk_penalty,
        evidence_quality=evidence_quality,
        model_source=signal.source,
    )


def fuse_outcome(
    outcome: ResearchOutcome,
    technical_score: Decimal,
    regime_multiplier: Decimal = Decimal("1"),
    valuation_score: Decimal | None = None,
) -> AlphaScore:
    """Fuse only an AVAILABLE outcome carrying a CertifiedAgentSignal."""
    if not outcome.available or outcome.certified_signal is None:
        raise ValueError(f"research outcome is not certified and available: {outcome.status.value}")
    return fuse(outcome.certified_signal, technical_score, regime_multiplier, valuation_score)


def rank(scores: list[AlphaScore]) -> list[AlphaScore]:
    return sorted(scores, key=lambda item: (-item.score, -item.confidence, item.ticker))