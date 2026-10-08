"""SPY-only deterministic market dimensions with versioned risk ceilings."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from meridian.quant.features import FeatureSnapshot
from meridian.quant.policy import QuantPolicy
from meridian.schemas import StableModel


class RegimeState(StableModel):
    version: str = "quant-regime-v2.1"
    as_of: datetime | None
    trend: Literal["TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND", "INSUFFICIENT_DATA"]
    volatility: Literal["NORMAL", "HIGH_VOLATILITY", "INSUFFICIENT_DATA"]
    drawdown_stress: bool = False
    risk_multiplier: Decimal = Field(ge=0, le=1)
    exposure_ceiling: Decimal = Field(ge=0, le=1)
    rebalance_urgency: str
    input_hash: str | None
    reasons: tuple[str, ...] = ()


def detect_regime(benchmark: FeatureSnapshot | None, policy: QuantPolicy) -> RegimeState:
    if benchmark is not None and benchmark.symbol != "SPY":
        raise ValueError("QUANT_REGIME_REQUIRES_SPY")
    required = ("trend_distance", "sma60_slope", "volatility_20", "volatility_percentile", "drawdown_252")
    if benchmark is None or benchmark.quality_status == "REJECTED" or any(benchmark.value(n) is None for n in required):
        return RegimeState(as_of=benchmark.as_of if benchmark else None, trend="INSUFFICIENT_DATA", volatility="INSUFFICIENT_DATA",
                           risk_multiplier=Decimal(0), exposure_ceiling=Decimal(0),
                           rebalance_urgency="BLOCKED", input_hash=benchmark.input_hash if benchmark else None,
                           reasons=("INSUFFICIENT_VERIFIED_SPY_HISTORY",))
    distance, slope, vol, percentile, dd = (benchmark.value(n) for n in required)
    if distance is None or slope is None or vol is None or percentile is None or dd is None:
        raise ValueError("REGIME_FEATURES_UNAVAILABLE")
    trend = "TRENDING_UP" if distance > policy.regime_trend_band and slope > 0 else "TRENDING_DOWN" if distance < -policy.regime_trend_band and slope < 0 else "RANGE_BOUND"
    high = vol >= policy.high_volatility_absolute or percentile >= policy.high_volatility_percentile
    stress = dd <= policy.risk_off_drawdown
    multiplier = Decimal(1)
    if trend == "TRENDING_DOWN" or stress:
        multiplier = min(multiplier, policy.downtrend_multiplier)
    if high:
        multiplier = min(multiplier, policy.high_volatility_multiplier)
    return RegimeState(as_of=benchmark.as_of, trend=trend, volatility="HIGH_VOLATILITY" if high else "NORMAL",
                       drawdown_stress=stress, risk_multiplier=multiplier,
                       exposure_ceiling=multiplier,
                       rebalance_urgency="RISK_REDUCTION" if multiplier < 1 else "NORMAL",
                       input_hash=benchmark.input_hash,
                       reasons=("SPY_TREND_AND_TRAILING_VOLATILITY", "TRAILING_DRAWDOWN_STRESS") if stress else ("SPY_TREND_AND_TRAILING_VOLATILITY",))
