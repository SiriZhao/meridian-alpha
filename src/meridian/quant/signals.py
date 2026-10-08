"""Explainable factor composition, robust ranks and explicit small-N fallback."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from meridian.quant.features import FactorValue, FeatureSnapshot
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import QuantPolicy
from meridian.quant.regime import RegimeState
from meridian.schemas import AlphaScore, StableModel

D = Decimal

if TYPE_CHECKING:
    from meridian.quant.features import ChallengerFeatureSnapshot
    from meridian.quant.policy import ChallengerPolicy


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

    @deterministic_decimal
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
    @deterministic_decimal
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


class ChallengerContribution(StableModel):
    version: str = "quant-factor-contribution.v2.2"
    name: str
    group: str
    symbol: str
    as_of: datetime
    availability_cutoff: datetime
    provenance: tuple[str, ...]
    lookback: int
    raw: Decimal | None
    normalized: Decimal | None
    weight: Decimal
    contribution: Decimal
    missing_reason: str | None
    transformation: str = "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"


class ChallengerScore(StableModel):
    version: str = "quant-score-v2.2"
    bridge: AlphaScoreV2
    signal_strength: Decimal = Field(ge=0, le=1)
    risk_adjusted_score: Decimal = Field(ge=0, le=1)
    factor_attribution: tuple[ChallengerContribution, ...]
    score_change_attribution: dict[str, Decimal]
    risk_score_change_attribution: dict[str, Decimal]
    positive_observations: int = Field(ge=0)
    persistence_definition: str = "CONSECUTIVE_OBSERVED_ELIGIBLE_SESSIONS_NOT_CONFIDENCE"
    policy_hash: str

    @model_validator(mode="after")
    @deterministic_decimal
    def coherent(self) -> "ChallengerScore":
        if self.bridge.predictive_confidence is not None:
            raise ValueError("CHALLENGER_PREDICTIVE_CONFIDENCE_UNCALIBRATED")
        if self.signal_strength != sum((c.contribution for c in self.factor_attribution), D(0)):
            raise ValueError("CHALLENGER_FACTOR_ATTRIBUTION_MISMATCH")
        if self.risk_adjusted_score != self.bridge.quant_score * self.bridge.risk_multiplier:
            raise ValueError("CHALLENGER_RISK_TRANSFORMATION_MISMATCH")
        if self.bridge.quant_score != (D(0) if self.bridge.exclusion_reasons else self.signal_strength):
            raise ValueError("CHALLENGER_ELIGIBILITY_MISMATCH")
        return self


@deterministic_decimal
def score_challenger(snapshots: Sequence["ChallengerFeatureSnapshot"], policy: "ChallengerPolicy",
                     regime: RegimeState, *, prior: Mapping[str, ChallengerScore] | None = None) -> tuple[ChallengerScore, ...]:
    from datetime import timedelta

    from meridian.trading_calendar import is_trading_session, latest_completed_session

    if len({s.base.symbol for s in snapshots}) != len(snapshots):
        raise ValueError("CHALLENGER_DUPLICATE_SYMBOL")
    if len({s.base.as_of for s in snapshots}) > 1 or any(regime.as_of != s.base.as_of for s in snapshots):
        raise ValueError("CHALLENGER_CUTOFF_MISMATCH")
    if prior and any(symbol != row.bridge.symbol or (snapshots and row.bridge.as_of >= snapshots[0].base.as_of)
                     or row.policy_hash != policy.digest for symbol, row in prior.items()):
        raise ValueError("CHALLENGER_PRIOR_IDENTITY_MISMATCH")
    specs = (("momentum_3m", "absolute", 63, policy.absolute_weight * D(".2"), D(".10")),
             ("momentum_6m", "absolute", 126, policy.absolute_weight * D(".3"), D(".10")),
             ("momentum_12_1", "absolute", 252, policy.absolute_weight * D(".5"), D(".10")),
             ("relative_momentum_6m", "relative", 126, policy.relative_weight, D(".10")),
             ("medium_distance", "trend", 60, policy.trend_weight / 2, D(".05")),
             ("trend_persistence", "trend", 60, policy.trend_weight / 2, D(".20")))
    def raw(snapshot: "ChallengerFeatureSnapshot", name: str) -> Decimal | None:
        value = snapshot.medium_distance if name == "medium_distance" else snapshot.base.value(name)
        return value - D(".5") if name == "trend_persistence" and value is not None else value
    populations = {n: [v for s in snapshots if s.base.quality_status != "REJECTED" and (v := raw(s, n)) is not None]
                   for n, _, _, _, _ in specs}
    rows = []
    for snapshot in sorted(snapshots, key=lambda s: s.base.symbol):
        base = snapshot.base
        excluded = list(base.reasons)
        if base.quality_status == "REJECTED":
            excluded.append("FEATURE_QUALITY_REJECTED")
        mom = base.value("momentum_6m")
        if mom is None or mom <= 0:
            excluded.append("ABSOLUTE_MOMENTUM_NOT_POSITIVE")
        volume = base.value("dollar_volume_20")
        if volume is None or volume < policy.controls.minimum_dollar_volume:
            excluded.append("LIQUIDITY_UNKNOWN_OR_BELOW_THRESHOLD")
        if regime.trend == "INSUFFICIENT_DATA":
            excluded.append("REGIME_UNKNOWN")
        contributions = []
        complete, strength = D(0), D(0)
        for name, group, lookback, weight, scale in specs:
            value = raw(snapshot, name)
            normalized = None
            method = "MISSING_ORIGINAL_WEIGHT_RETAINED"
            if value is not None and populations[name]:
                population = populations[name]
                absolute = (1 + value / (abs(value) + scale)) / 2
                n = len(population)
                rank = (D(sum(v < value for v in population)) + D(sum(v == value for v in population)) / 2) / n
                blend = policy.maximum_rank_blend * (n - 1) / (n + 4)
                normalized = (1 - blend) * absolute + blend * rank
                method = "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
                if group in policy.neutral_groups:
                    normalized, method = D(".5"), "PREDECLARED_NEUTRAL_GROUP_ABLATION"
                complete += weight
            amount = weight * normalized if normalized is not None else D(0)
            strength += amount
            contributions.append(ChallengerContribution(name=name, group=group, symbol=base.symbol, as_of=base.as_of,
                availability_cutoff=snapshot.availability_cutoff, provenance=snapshot.provenance, lookback=lookback,
                raw=value, normalized=normalized, weight=weight, contribution=amount,
                missing_reason="INPUT_UNAVAILABLE_NO_REWEIGHTING" if value is None else None, transformation=method))
        vol = base.value("volatility_60")
        if vol is None:
            excluded.append("VOLATILITY_UNKNOWN")
        multiplier = (min(D(1), policy.controls.target_volatility / max(vol, policy.controls.volatility_floor))
                      if vol is not None else D(0)) * regime.risk_multiplier
        eligible_strength = D(0) if excluded else strength
        previous = (prior or {}).get(base.symbol)
        changes = {}
        if previous:
            old = {c.name: c.contribution for c in previous.factor_attribution}
            changes = {c.name: c.contribution - old[c.name] for c in contributions}
            changes["eligibility"] = (eligible_strength - strength) - (
                previous.bridge.quant_score - previous.signal_strength)
        consecutive = False
        if previous:
            cursor = latest_completed_session(previous.bridge.as_of) + timedelta(days=1)
            while not is_trading_session(cursor):
                cursor += timedelta(days=1)
            consecutive = cursor == base.last_session
        bridge = AlphaScoreV2(symbol=base.symbol, as_of=base.as_of, strategy="V22", policy_version=policy.version,
            quant_score=eligible_strength, relative_rank=1, contributions=(), data_quality_status=base.quality_status,
            completeness=complete, risk_multiplier=multiplier,
            risk_adjustments=("RISK_ADJUSTED_SCORE_IS_REPORTED_SEPARATELY", "VOLATILITY_AND_REGIME_ARE_NOT_ALPHA"),
            inclusion_reasons=("POSITIVE_ABSOLUTE_MOMENTUM_AND_QUALIFIED_LIQUIDITY",) if not excluded else (),
            exclusion_reasons=tuple(sorted(set(excluded))),
            score_change=eligible_strength - previous.bridge.quant_score if previous else None, input_hash=snapshot.input_hash)
        rows.append(ChallengerScore(bridge=bridge, signal_strength=strength,
            risk_adjusted_score=eligible_strength * multiplier, factor_attribution=tuple(contributions),
            score_change_attribution=changes, policy_hash=policy.digest,
            risk_score_change_attribution={"signal_and_eligibility": (eligible_strength - previous.bridge.quant_score) * multiplier,
                "risk_transform": previous.bridge.quant_score * (multiplier - previous.bridge.risk_multiplier)} if previous else {},
            positive_observations=(previous.positive_observations if previous and latest_completed_session(previous.bridge.as_of) == base.last_session
                                  else previous.positive_observations + 1 if previous and consecutive else 1) if eligible_strength > 0 else 0))
    return tuple(row.model_copy(update={"bridge": row.bridge.model_copy(update={"relative_rank": i})})
                 for i, row in enumerate(sorted(rows, key=lambda r: (-r.bridge.quant_score, r.bridge.symbol)), 1))
