"""Risk/performance metrics and paired moving-block uncertainty, no alpha claims."""

import math
import random
from collections.abc import Sequence
from statistics import mean, stdev

from meridian.quant.backtest import ReplayResult


def paired_block_interval(left: Sequence[float], right: Sequence[float], *, block: int = 20,
                          repetitions: int = 500, seed: int = 1729) -> dict[str, object]:
    if len(left) != len(right) or block < 1 or repetitions < 20:
        raise ValueError("BOOTSTRAP_INVALID_INPUT")
    if len(left) < 2 * block:
        return {"status": "INSUFFICIENT_DEPENDENT_BLOCKS", "interval": None, "block_sessions": block}
    if any(not math.isfinite(v) for v in (*left, *right)):
        raise ValueError("BOOTSTRAP_NONFINITE_INPUT")
    differences = [a - b for a, b in zip(left, right, strict=True)]
    rng = random.Random(seed)
    estimates = []
    for _ in range(repetitions):
        sample = []
        while len(sample) < len(differences):
            start = rng.randrange(len(differences) - block + 1)
            sample.extend(differences[start:start + block])
        estimates.append(mean(sample[:len(differences)]) * 252)
    estimates.sort()
    return {"status": "DESCRIPTIVE_POINTWISE_NOT_MULTIPLE_TEST_CORRECTED",
            "interval": [estimates[int(repetitions * .025)], estimates[min(repetitions - 1, int(repetitions * .975))]],
            "block_sessions": block, "repetitions": repetitions, "seed": seed,
            "estimand": "ANNUALIZED_MEAN_PAIRED_DAILY_RETURN_DIFFERENCE"}


def performance(result: ReplayResult) -> dict[str, object]:
    if not result.days:
        return {"status": "INSUFFICIENT_OBSERVATIONS"}
    returns = [float(d.daily_return) for d in result.days]
    benchmarks = [float(d.benchmark_return) for d in result.days]
    excess = [a - b for a, b in zip(returns, benchmarks, strict=True)]
    navs = [float(result.initial_nav), *(float(d.nav) for d in result.days)]
    annual_vol = stdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
    tracking = stdev(excess) * math.sqrt(252) if len(excess) > 1 else 0.0
    downside = math.sqrt(mean([min(0.0, r) ** 2 for r in returns]) * 252)
    cagr = (navs[-1] / navs[0]) ** (252 / len(returns)) - 1
    peak = navs[0]
    drawdown = 0.0
    for nav in navs[1:]:
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
    sorted_returns = sorted(returns)
    tail = sorted_returns[:max(1, math.ceil(len(returns) * .05))]
    regimes = {}
    for regime in sorted({d.regime for d in result.days}):
        subset = [float(d.daily_return) for d in result.days if d.regime == regime]
        regimes[regime] = {"sessions": len(subset), "mean_daily_return": mean(subset), "worst_day": min(subset)}
    ic = [float(d.factor_ic) for d in result.days if d.factor_ic is not None]
    return {"status": result.evidence_status, "sessions": len(returns), "CAGR": cagr,
            "annualized_volatility": annual_vol,
            "Sharpe": mean(returns) * 252 / annual_vol if annual_vol > 0 else None,
            "Sortino": mean(returns) * 252 / downside if downside > 0 else None,
            "max_drawdown": drawdown, "Calmar": cagr / abs(drawdown) if drawdown < 0 else None,
            "cumulative_return": navs[-1] / navs[0] - 1,
            "cumulative_excess_return": navs[-1] / navs[0] - math.prod(1 + r for r in benchmarks),
            "tracking_error": tracking, "information_ratio": mean(excess) * 252 / tracking if tracking > 0 else None,
            "gross_turnover": sum(float(d.turnover) for d in result.days),
            "transaction_costs": sum(float(d.costs) for d in result.days),
            "mean_exposure": mean(float(d.exposure) for d in result.days),
            "risk_drift_sessions": sum(bool(d.risk_drift) for d in result.days),
            "blocked_decision_sessions": sum(d.decision == "BLOCKED" for d in result.days),
            "cash_utilization": mean(float(d.exposure) for d in result.days),
            "hit_rate_positive_day": sum(r > 0 for r in returns) / len(returns),
            "factor_IC_1_session_mean": mean(ic) if ic else None,
            "factor_IC_sessions": len(ic), "downside_deviation": downside,
            "return_distribution": {"worst": min(returns), "best": max(returns), "median": sorted_returns[len(returns) // 2],
                                    "5pct_quantile": sorted_returns[min(len(returns) - 1, int(len(returns) * .05))], "expected_shortfall_5pct": mean(tail)},
            "regime_stability": regimes, "risk_free_assumption": "ZERO_NO_TREASURY_SERIES",
            "uncertainty_vs_SPY": [paired_block_interval(returns, benchmarks, block=b) for b in (5, 20, 60)],
            "independent_sample_warning": "DAILY_AND_FACTOR_IC_ROWS_ARE_SERIAL_AND_CROSS_SECTIONALLY_DEPENDENT"}
