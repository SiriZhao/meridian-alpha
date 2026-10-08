"""Point-in-time price factors from existing project-owned historical bars.

No forward filling, inferred volume, retrospective availability, or valuation.
All returns require an explicitly verified fully adjusted price basis.
"""

import hashlib
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from meridian.historical import (
    HistoricalAdjustmentStatus,
    HistoricalBar,
    HistoricalBarCertification,
    HistoricalBarSeries,
    HistoricalQuality,
)
from meridian.quant.numerics import deterministic_decimal
from meridian.schemas import StableModel
from meridian.trading_calendar import is_trading_session, latest_completed_session, session_close

D = Decimal
ANNUAL = D(252)


def mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, D(0)) / len(values)


def volatility(values: Sequence[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    average = mean(values)
    return (sum(((v - average) ** 2 for v in values), D(0)) / (len(values) - 1) * ANNUAL).sqrt()


class FactorValue(StableModel):
    name: str
    version: Literal["price-factor-v2.1"] = "price-factor-v2.1"
    symbol: str
    as_of: datetime
    lookback: int = Field(ge=1)
    raw_value: Decimal | None
    normalized_value: Decimal | None = None
    provenance: tuple[str, ...] = ()
    availability_cutoff: datetime
    quality_status: Literal["AVAILABLE", "UNAVAILABLE"]
    missing_reason: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> "FactorValue":
        if self.availability_cutoff > self.as_of:
            raise ValueError("FACTOR_FUTURE_AVAILABILITY")
        if self.raw_value is None and not self.missing_reason:
            raise ValueError("FACTOR_MISSING_REASON_REQUIRED")
        if (self.raw_value is not None) != (self.quality_status == "AVAILABLE"):
            raise ValueError("FACTOR_VALUE_QUALITY_MISMATCH")
        return self


class FeatureSnapshot(StableModel):
    version: Literal["quant-features-v2.1"] = "quant-features-v2.1"
    symbol: str
    as_of: datetime
    last_session: date | None
    factors: tuple[FactorValue, ...]
    input_hash: str
    quality_status: Literal["VERIFIED", "REJECTED", "SYNTHETIC_DIAGNOSTIC"]
    reasons: tuple[str, ...] = ()
    synthetic: bool = False

    def value(self, name: str) -> Decimal | None:
        return next((f.raw_value for f in self.factors if f.name == name), None)

    @model_validator(mode="after")
    def lineage(self) -> "FeatureSnapshot":
        if len({f.name for f in self.factors}) != len(self.factors):
            raise ValueError("DUPLICATE_FACTOR")
        if {f.name for f in self.factors} != set(FACTOR_LOOKBACKS):
            raise ValueError("SNAPSHOT_FACTOR_CONTRACT_INCOMPLETE")
        if any(f.symbol != self.symbol or f.as_of != self.as_of for f in self.factors):
            raise ValueError("FACTOR_SNAPSHOT_IDENTITY_MISMATCH")
        if self.quality_status == "VERIFIED" and self.synthetic:
            raise ValueError("SYNTHETIC_SNAPSHOT_CANNOT_BE_VERIFIED_MARKET_DATA")
        return self


FACTOR_LOOKBACKS = {
    "return_1d": 1, "momentum_1m": 21, "momentum_3m": 63,
    "momentum_6m": 126, "momentum_12m": 252, "momentum_12_1": 252,
    "relative_momentum_6m": 126, "risk_adjusted_momentum": 126,
    "sma20": 20, "sma60": 60, "sma200": 200, "trend_distance": 200,
    "sma60_slope": 80, "trend_persistence": 60, "breakout_distance": 60,
    "volatility_20": 20, "volatility_60": 60, "downside_deviation": 60,
    "atr14": 14, "drawdown_60": 60, "drawdown_252": 252,
    "relative_volatility": 60, "beta_60": 60, "correlation_60": 60,
    "dollar_volume_20": 20, "volatility_percentile": 252, "reversal_5d": 5,
}


def eligible_bars(series: HistoricalBarSeries, cutoff: datetime) -> tuple[HistoricalBar, ...]:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("QUANT_CUTOFF_TIMEZONE_REQUIRED")
    # A later retrieval of a genuinely archived PIT row is allowed. Its known-at
    # and actual observation times must precede the decision, not retrieval.
    return tuple(sorted((bar for bar in series.bars if bar.available_at <= cutoff
                         and bar.observed_at <= cutoff and session_close(bar.session, bar.calendar) <= cutoff),
                        key=lambda b: b.session))


def _quality(series: HistoricalBarSeries, bars: tuple[HistoricalBar, ...], cutoff: datetime,
             diagnostic: bool) -> tuple[str, ...]:
    reasons = []
    if not bars:
        return ("NO_AVAILABLE_COMPLETED_BARS",)
    if any(b.canonical_symbol != series.canonical_symbol for b in bars):
        reasons.append("SYMBOL_MISMATCH")
    if any(b.currency != "USD" for b in bars):
        reasons.append("NON_USD_SERIES")
    if any(min(b.open, b.high, b.low, b.close) <= 0 for b in bars):
        reasons.append("NONPOSITIVE_PRICE")
    if any(b.observed_at < session_close(b.session, b.calendar) or b.available_at < b.observed_at for b in bars):
        reasons.append("PREMATURE_BAR_AVAILABILITY")
    if any(b.adjustment_status != HistoricalAdjustmentStatus.FULLY_ADJUSTED_OHLCV for b in bars):
        reasons.append("UNVERIFIED_ADJUSTMENT_BASIS")
    permitted = {HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED}
    if diagnostic:
        permitted.add(HistoricalBarCertification.SYNTHETIC)
    if any(b.certification not in permitted or b.quality != HistoricalQuality.VERIFIED for b in bars):
        reasons.append("UNVERIFIED_PRICE_SERIES")
    if bars[-1].session != latest_completed_session(cutoff, bars[-1].calendar):
        reasons.append("STALE_HISTORY")
    cursor = bars[0].session
    actual = {b.session for b in bars}
    while cursor <= bars[-1].session:
        if is_trading_session(cursor, bars[-1].calendar) and cursor not in actual:
            reasons.append("MISSING_SESSION_NO_FORWARD_FILL")
            break
        cursor += timedelta(days=1)
    return tuple(reasons)


@deterministic_decimal
def compute_features(series: HistoricalBarSeries, cutoff: datetime, *,
                     benchmark: HistoricalBarSeries | None = None,
                     diagnostic: bool = False) -> FeatureSnapshot:
    """Compute from only the latest 253 eligible, contiguous completed sessions."""
    return _compute(series, cutoff, benchmark=benchmark, diagnostic=diagnostic)


def _compute(series: HistoricalBarSeries, cutoff: datetime, *,
             benchmark: HistoricalBarSeries | None, diagnostic: bool) -> FeatureSnapshot:
    bars = eligible_bars(series, cutoff)[-253:]
    reasons = _quality(series, bars, cutoff, diagnostic)
    bench_bars = eligible_bars(benchmark, cutoff)[-253:] if benchmark is not None else ()
    synthetic = any(b.certification == HistoricalBarCertification.SYNTHETIC for b in bars + bench_bars)
    if benchmark is not None and benchmark.canonical_symbol != "SPY":
        raise ValueError("QUANT_BENCHMARK_MUST_BE_SPY")
    bench_ok = benchmark is not None and not _quality(benchmark, bench_bars, cutoff, diagnostic)
    encoded = "|".join(b.stable_json() for b in bars + bench_bars)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    provenance = tuple(sorted({b.provider + ":" + b.source for b in bars + bench_bars})) + (digest,)
    availability = max((b.available_at for b in bars + bench_bars), default=cutoff)
    prices = [b.close for b in bars]
    returns = [right / left - 1 for left, right in zip(prices, prices[1:], strict=False)] if not reasons else []
    values: dict[str, Decimal | None] = dict.fromkeys(FACTOR_LOOKBACKS)
    missing: dict[str, str] = {}
    if not reasons:
        for name, n in (("return_1d", 1), ("momentum_1m", 21), ("momentum_3m", 63),
                        ("momentum_6m", 126), ("momentum_12m", 252), ("reversal_5d", 5)):
            if len(prices) > n:
                values[name] = prices[-1] / prices[-n - 1] - 1
        if len(prices) > 252:
            values["momentum_12_1"] = prices[-22] / prices[-253] - 1
        for n in (20, 60, 200):
            if len(prices) >= n:
                values[f"sma{n}"] = mean(prices[-n:])
        if values["sma200"] is not None:
            values["trend_distance"] = prices[-1] / values["sma200"] - 1
        if len(prices) >= 80:
            values["sma60_slope"] = mean(prices[-60:]) / mean(prices[-80:-20]) - 1
        if len(returns) >= 60:
            values["trend_persistence"] = D(sum(r > 0 for r in returns[-60:])) / 60
            values["breakout_distance"] = prices[-1] / max(prices[-60:]) - 1
            values["downside_deviation"] = (mean([min(D(0), r) ** 2 for r in returns[-60:]]) * ANNUAL).sqrt()
        for n in (20, 60):
            if len(returns) >= n:
                values[f"volatility_{n}"] = volatility(returns[-n:])
        for n in (60, 252):
            if len(prices) >= n:
                peak = prices[-n]
                deepest = D(0)
                for price in prices[-n:]:
                    peak = max(peak, price)
                    deepest = min(deepest, price / peak - 1)
                values[f"drawdown_{n}"] = deepest
        if len(bars) >= 15:
            values["atr14"] = mean([max(b.high - b.low, abs(b.high - prev.close), abs(b.low - prev.close))
                                    for prev, b in zip(bars[-15:-1], bars[-14:], strict=True)])
        if len(bars) >= 20:
            if all(b.volume > 0 for b in bars[-20:]):
                values["dollar_volume_20"] = mean([b.close * b.volume for b in bars[-20:]])
            else:
                missing["dollar_volume_20"] = "ZERO_OR_UNAVAILABLE_VOLUME"
        vol = values["volatility_60"]
        mom = values["momentum_6m"]
        if vol is not None and vol > 0 and mom is not None:
            values["risk_adjusted_momentum"] = mom / vol
        if len(returns) >= 252:
            trailing = [volatility(returns[i - 20:i]) for i in range(20, len(returns) + 1)]
            current = trailing[-1]
            assert current is not None
            values["volatility_percentile"] = D(sum(v is not None and v <= current for v in trailing)) / len(trailing)
        if bench_ok and [b.session for b in bars] == [b.session for b in bench_bars]:
            bench_prices = [b.close for b in bench_bars]
            br = [right / left - 1 for left, right in zip(bench_prices, bench_prices[1:], strict=False)]
            if len(prices) > 126 and mom is not None:
                values["relative_momentum_6m"] = mom - (bench_prices[-1] / bench_prices[-127] - 1)
            if len(br) >= 60 and vol is not None:
                x, y = returns[-60:], br[-60:]
                mx, my = mean(x), mean(y)
                vx = sum(((r - mx) ** 2 for r in x), D(0))
                vy = sum(((r - my) ** 2 for r in y), D(0))
                cov = sum(((a - mx) * (b - my) for a, b in zip(x, y, strict=True)), D(0))
                if vy > 0:
                    values["beta_60"] = cov / vy
                    values["relative_volatility"] = vol / (vy / 59 * ANNUAL).sqrt()
                if vx > 0 and vy > 0:
                    values["correlation_60"] = max(D(-1), min(D(1), cov / (vx * vy).sqrt()))
        else:
            for name in ("relative_momentum_6m", "relative_volatility", "beta_60", "correlation_60"):
                missing[name] = "BENCHMARK_MISSING_UNVERIFIED_OR_UNALIGNED"
    factors = tuple(FactorValue(name=name, symbol=series.canonical_symbol, as_of=cutoff,
                               lookback=n, raw_value=values[name], provenance=provenance,
                               availability_cutoff=availability,
                               quality_status="AVAILABLE" if values[name] is not None else "UNAVAILABLE",
                               missing_reason=None if values[name] is not None else
                               ";".join(reasons) if reasons else missing.get(name, "INSUFFICIENT_HISTORY_OR_ZERO_VARIANCE"))
                    for name, n in FACTOR_LOOKBACKS.items())
    return FeatureSnapshot(symbol=series.canonical_symbol, as_of=cutoff,
                           last_session=bars[-1].session if bars else None, factors=factors,
                           input_hash=digest, quality_status="REJECTED" if reasons else "SYNTHETIC_DIAGNOSTIC" if synthetic else "VERIFIED",
                           reasons=reasons, synthetic=synthetic)


class ChallengerFeatureSnapshot(StableModel):
    version: Literal["quant-features-v2.2"] = "quant-features-v2.2"
    base: FeatureSnapshot
    # None retains explicit unknown semantics; never zero-fill these observations.
    medium_distance: Decimal | None
    momentum_acceleration: Decimal | None
    trend_instability: Decimal | None
    residual_momentum_63: Decimal | None
    missing_reasons: dict[str, str]
    provenance: tuple[str, ...]
    availability_cutoff: datetime
    input_hash: str

    @model_validator(mode="after")
    def coherent(self) -> "ChallengerFeatureSnapshot":
        if self.availability_cutoff > self.base.as_of:
            raise ValueError("CHALLENGER_FUTURE_FEATURE")
        for name in ("medium_distance", "momentum_acceleration", "trend_instability", "residual_momentum_63"):
            if getattr(self, name) is None and name not in self.missing_reasons:
                raise ValueError("CHALLENGER_MISSING_FEATURE_REASON")
        return self


@deterministic_decimal
def compute_challenger_features(series: HistoricalBarSeries, cutoff: datetime, *,
                                benchmark: HistoricalBarSeries | None = None,
                                diagnostic: bool = False) -> ChallengerFeatureSnapshot:
    base = compute_features(series, cutoff, benchmark=benchmark, diagnostic=diagnostic)
    sessions = [b.session for b in series.bars if b.available_at <= cutoff and b.observed_at <= cutoff
                and session_close(b.session, b.calendar) <= cutoff]
    if sessions != sorted(sessions):
        raise ValueError("CHALLENGER_OUT_OF_SEQUENCE_BARS")
    if benchmark is not None:
        bench_sessions = [b.session for b in benchmark.bars if b.available_at <= cutoff and b.observed_at <= cutoff
                          and session_close(b.session, b.calendar) <= cutoff]
        if bench_sessions != sorted(bench_sessions):
            raise ValueError("CHALLENGER_OUT_OF_SEQUENCE_BENCHMARK")
    bars = eligible_bars(series, cutoff)[-253:]
    bench = eligible_bars(benchmark, cutoff)[-253:] if benchmark else ()
    values: dict[str, Decimal | None] = dict.fromkeys(
        ("medium_distance", "momentum_acceleration", "trend_instability", "residual_momentum_63"))
    if base.quality_status != "REJECTED":
        prices = [b.close for b in bars]
        sma = base.value("sma60")
        if sma is not None:
            values["medium_distance"] = prices[-1] / sma - 1
        if len(prices) > 126:
            # Difference between consecutive 63-session simple returns.
            values["momentum_acceleration"] = prices[-1] / prices[-64] - prices[-64] / prices[-127]
        if len(prices) >= 80:
            signs = [prices[i] > mean(prices[i - 59:i + 1]) for i in range(len(prices) - 21, len(prices))]
            values["trend_instability"] = D(sum(a != b for a, b in zip(signs, signs[1:], strict=False))) / 20
        beta = base.value("beta_60")
        # Validated base beta requires fully aligned, certified benchmark rows.
        if beta is not None and len(prices) > 63 and [b.session for b in bars] == [b.session for b in bench]:
            stock = [b.close / a.close - 1 for a, b in zip(bars[-64:-1], bars[-63:], strict=True)]
            market = [b.close / a.close - 1 for a, b in zip(bench[-64:-1], bench[-63:], strict=True)]
            values["residual_momentum_63"] = sum((x - beta * y for x, y in zip(stock, market, strict=True)), D(0))
    missing = {n: "INVALID_OR_INSUFFICIENT_PIT_HISTORY_OR_BENCHMARK" for n, v in values.items() if v is None}
    payload = base.stable_json() + "|" + "|".join(f"{n}:{values[n]}" for n in sorted(values))
    return ChallengerFeatureSnapshot(base=base, medium_distance=values["medium_distance"],
        momentum_acceleration=values["momentum_acceleration"], trend_instability=values["trend_instability"],
        residual_momentum_63=values["residual_momentum_63"], missing_reasons=missing,
        provenance=tuple(sorted({p for f in base.factors for p in f.provenance})),
        availability_cutoff=max((f.availability_cutoff for f in base.factors), default=cutoff),
        input_hash=hashlib.sha256(payload.encode()).hexdigest())
