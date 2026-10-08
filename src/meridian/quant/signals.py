"""Explainable factor composition, robust ranks and explicit small-N fallback."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from meridian.quant.features import FactorValue, FeatureSnapshot
from meridian.quant.policy import QuantPolicy
from meridian.quant.regime import RegimeState
from meridian.schemas import AlphaScore, StableModel

D = Decimal


class FactorContribution(StableModel):
    factor: FactorValue
    group: str
    weight: Decimal
    contribution: Decimal
    normalization: str


class AlphaScoreV2(StableModel):
    symbol: str
    as_of: datetime
    strategy: str
    policy_version: str
    quant_score: Decimal = Field(ge=0, le=1)
    relative_rank: int = Field(ge=1)
    contributions: tuple[FactorContribution, ...]
    data_quality_status: str
    completeness: Decimal
    risk_multiplier: Decimal
    risk_adjustments: tuple[str, ...]
    inclusion_reasons: tuple[str, ...]
    exclusion_reasons: tuple[str, ...]
    score_change: Decimal | None = None
    input_hash: str
    predictive_confidence: Decimal | None = None

    def domain_score(self) -> AlphaScore:
        return AlphaScore(ticker=self.symbol, score=self.quant_score,
                          confidence=D(0), expected_direction="BULLISH" if self.quant_score > 0 else "NEUTRAL",
                          evidence_quality=self.completeness, risk_penalty=1 - self.risk_multiplier,
                          model_source="DETERMINISTIC_QUANT_V2_UNCALIBRATED")


def _normalize(value: Decimal, population: Sequence[Decimal], scale: Decimal, minimum: int) -> tuple[Decimal, str]:
    if len(population) < minimum or min(population) == max(population):
        # A monotone bounded absolute transform has a declared scale and remains
        # stable for one symbol or tied samples; no sample standard deviation.
        return value / (abs(value) + scale), "ABSOLUTE_BOUNDED_SMALL_N_OR_TIES"
    below = sum(x < value for x in population)
    equal = sum(x == value for x in population)
    percentile = (D(below) + D(equal - 1) / 2) / (len(population) - 1)
    return 2 * percentile - 1, "TIED_MIDRANK_PERCENTILE"


class QuantFactorEngine:
    def score(self, snapshots: Sequence[FeatureSnapshot], policy: QuantPolicy, regime: RegimeState,
              *, prior: Mapping[str, AlphaScoreV2] | None = None) -> tuple[AlphaScoreV2, ...]:
        if len({s.symbol for s in snapshots}) != len(snapshots):
            raise ValueError("QUANT_DUPLICATE_SYMBOL")
        if len({s.as_of for s in snapshots}) > 1:
            raise ValueError("QUANT_MIXED_CUTOFFS")
        if snapshots and regime.as_of is not None and regime.as_of != snapshots[0].as_of:
            raise ValueError("QUANT_REGIME_CUTOFF_MISMATCH")
        if prior and any(row.symbol != symbol or (snapshots and row.as_of >= snapshots[0].as_of)
                         for symbol, row in prior.items()):
            raise ValueError("QUANT_PRIOR_SCORE_NOT_PRIOR")
        if policy.strategy == "A0":
            specifications = (("return_1d", "operational", D(1), policy.momentum_scale),)
        else:
            momentum_weight = D(1) if policy.strategy == "A1" else policy.momentum_weight
            specs = []
            if policy.use_momentum:
                specs.extend((n, "momentum", momentum_weight / 2, policy.momentum_scale)
                             for n in ("momentum_6m", "momentum_12_1"))
            if policy.strategy != "A1" and policy.use_trend:
                specs.extend((n, "trend", policy.trend_weight / 2, policy.trend_scale)
                             for n in ("trend_distance", "sma60_slope"))
            specifications = tuple(specs)
        populations = {name: [s.value(name) for s in snapshots if s.quality_status != "REJECTED" and s.value(name) is not None]
                       for name, _, _, _ in specifications}
        rows = []
        for snapshot in sorted(snapshots, key=lambda s: s.symbol):
            excluded = list(snapshot.reasons)
            adjustments = []
            contributions = []
            completeness = D(0)
            score = D(0)
            for name, group, weight, scale in specifications:
                factor = next(f for f in snapshot.factors if f.name == name)
                if factor.raw_value is None:
                    contributions.append(FactorContribution(factor=factor, group=group, weight=weight,
                                                           contribution=D(0), normalization="MISSING_EXPLICIT_PENALTY"))
                    continue
                if policy.strategy == "A0":
                    normalized, method = max(D(0), factor.raw_value), "POSITIVE_DAILY_RETURN_BASELINE"
                else:
                    population = [v for v in populations[name] if v is not None]
                    normalized, method = _normalize(factor.raw_value, population, scale, policy.cross_section_minimum)
                    # Convert signed factor strength to [0,1]; absolute positive
                    # momentum remains a separate eligibility gate.
                    normalized = (normalized + 1) / 2
                amount = weight * normalized
                score += amount
                completeness += weight
                contributions.append(FactorContribution(factor=factor.model_copy(update={"normalized_value": normalized}),
                                                       group=group, weight=weight, contribution=amount, normalization=method))
            if not specifications:
                excluded.append("ALL_ALPHA_GROUPS_DISABLED")
            if policy.strategy != "A0":
                momentum = snapshot.value("momentum_6m")
                if policy.use_momentum and (momentum is None or momentum <= 0):
                    excluded.append("NONPOSITIVE_OR_MISSING_MEDIUM_MOMENTUM")
                volume = snapshot.value("dollar_volume_20")
                if volume is None:
                    excluded.append("LIQUIDITY_UNKNOWN")
                elif volume < policy.minimum_dollar_volume:
                    excluded.append("LIQUIDITY_BELOW_POLICY")
            multiplier = D(1)
            if policy.strategy in {"A3", "A4"} and policy.use_volatility_adjustment:
                vol = snapshot.value("volatility_60")
                if vol is None:
                    excluded.append("VOLATILITY_UNKNOWN")
                else:
                    multiplier = min(D(1), policy.target_volatility / max(vol, policy.volatility_floor))
                    adjustments.append("TARGET_TO_REALIZED_VOLATILITY_MULTIPLIER")
            if policy.strategy == "A4":
                multiplier *= regime.risk_multiplier
                adjustments.append("SPY_REGIME_MULTIPLIER")
                if regime.trend == "INSUFFICIENT_DATA":
                    excluded.append("REGIME_INSUFFICIENT_DATA")
            if completeness < 1:
                adjustments.append("MISSING_FACTORS_KEEP_ORIGINAL_WEIGHTS_NO_RENORMALIZATION")
            final = D(0) if excluded else min(D(1), max(D(0), score * multiplier))
            previous = (prior or {}).get(snapshot.symbol)
            rows.append(AlphaScoreV2(symbol=snapshot.symbol, as_of=snapshot.as_of, strategy=policy.strategy,
                                    policy_version=policy.version, quant_score=final, relative_rank=1,
                                    contributions=tuple(contributions), data_quality_status=snapshot.quality_status,
                                    completeness=completeness, risk_multiplier=multiplier, risk_adjustments=tuple(adjustments),
                                    inclusion_reasons=("POSITIVE_DETERMINISTIC_ALPHA",) if final > 0 else (),
                                    exclusion_reasons=tuple(excluded) or (() if final > 0 else ("NONPOSITIVE_ALPHA",)),
                                    score_change=final - previous.quant_score if previous else None, input_hash=snapshot.input_hash))
        return tuple(row.model_copy(update={"relative_rank": i})
                     for i, row in enumerate(sorted(rows, key=lambda r: (-r.quant_score, r.symbol)), 1))
