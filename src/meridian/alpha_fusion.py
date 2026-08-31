"""Deterministic fusion of certified research and quant features."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from meridian.authorization import CertifiedAgentSignal
from meridian.research import ResearchOutcome
from meridian.schemas import AgentSignal, AlphaScore, ProductionAlphaDecision

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


def _fusion_components(
    certified: CertifiedAgentSignal,
    technical_score: Decimal,
    regime_multiplier: Decimal,
    dislocation_modifier: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Compute one authoritative set of quant/research/final components."""

    signal = certified.signal
    quant_component = Decimal("0.45") * max(Decimal("-1"), min(Decimal("1"), technical_score))
    base = research_modifier(certified, regime_multiplier=regime_multiplier)
    combined = combine_research_modifiers(base, dislocation_modifier)
    effective_dislocation = combined - base
    risk_penalty = signal.risk_score if signal.risk_score is not None else Decimal("0")
    final = max(Decimal("-1"), min(Decimal("1"), quant_component + combined - risk_penalty))
    quant_only = max(Decimal("-1"), min(Decimal("1"), quant_component - risk_penalty))
    return quant_component, quant_only, base, effective_dislocation, final


def fuse(
    certified: CertifiedAgentSignal | AgentSignal,
    technical_score: Decimal,
    regime_multiplier: Decimal = Decimal("1"),
    valuation_score: Decimal | None = None,
    dislocation_modifier: Decimal = Decimal("0"),
) -> AlphaScore:
    """Fuse only a certified signal; plain AgentSignal input is rejected."""
    if not isinstance(certified, CertifiedAgentSignal):
        raise TypeError("Alpha Fusion requires CertifiedAgentSignal")
    signal = certified.signal
    _ = valuation_score  # valuation has no independent path outside certified signal evidence.
    _, _, _, _, score = _fusion_components(
        certified, technical_score, regime_multiplier, dislocation_modifier
    )
    evidence_quality = min(Decimal("1"), Decimal(len(signal.evidence)) / Decimal("3")) if signal.evidence else Decimal("0")
    risk_penalty = signal.risk_score if signal.risk_score is not None else Decimal("0")
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


def fuse_production_decision(
    certified: CertifiedAgentSignal,
    *,
    run_id: str,
    quant_score: Decimal,
    policy_hash: str,
    quant_input: object | None = None,
    quant_input_hash: str | None = None,
    response_artifact_hash: str | None = None,
    regime_multiplier: Decimal = Decimal("1"),
    dislocation_modifier: Decimal = Decimal("0"),
) -> ProductionAlphaDecision:
    """Emit the production lineage object from the same AlphaFusion math."""

    if not isinstance(certified, CertifiedAgentSignal):
        raise TypeError("ProductionAlphaDecision requires CertifiedAgentSignal")
    if not quant_input_hash:
        encoded = json.dumps(quant_input if quant_input is not None else {"quant_score": str(quant_score)}, sort_keys=True, separators=(",", ":"), default=str)
        quant_input_hash = hashlib.sha256(encoded.encode()).hexdigest()
    _, quant_only, base, effective_dislocation, final = _fusion_components(
        certified, quant_score, regime_multiplier, dislocation_modifier
    )
    return ProductionAlphaDecision(
        ticker=certified.ticker,
        run_id=run_id,
        decision_as_of=certified.as_of,
        quant_score=quant_score,
        quant_only_alpha=quant_only,
        quant_input_hash=quant_input_hash,
        certified_signal_id=certified.certificate_id,
        research_direction=certified.direction,
        research_conviction=certified.signal.conviction,
        research_modifier=base,
        dislocation_modifier=effective_dislocation,
        combined_research_modifier=base + effective_dislocation,
        risk_penalty=certified.signal.risk_score or Decimal("0"),
        final_alpha=final,
        policy_hash=policy_hash,
        evidence_ids=certified.evidence_ids,
        response_artifact_hash=response_artifact_hash,
    )


def rank(scores: list[AlphaScore]) -> list[AlphaScore]:
    return sorted(scores, key=lambda item: (-item.score, -item.confidence, item.ticker))
