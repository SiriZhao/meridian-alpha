"""Additional descriptive metrics; uncertainty never confers financial eligibility."""
import math
from statistics import mean

from meridian.quant.backtest import ReplayResult
from meridian.quant.metrics import performance


def flagship_metrics(result: ReplayResult) -> dict[str, object]:
    base = performance(result)
    if not result.days:
        return base
    returns = [float(d.daily_return) for d in result.days]
    benchmark = [float(d.benchmark_return) for d in result.days]
    if any(not math.isfinite(v) or v < -1 for v in (*returns, *benchmark)):
        raise ValueError('V23_METRIC_INVALID_RETURN')
    peak = float(result.initial_nav)
    drawdowns = []
    for day in result.days:
        peak = max(peak, float(day.nav))
        drawdowns.append(float(day.nav) / peak - 1)
    bm = mean(benchmark)
    variance = sum((r - bm) ** 2 for r in benchmark)
    rm = mean(returns)
    beta = sum((r - rm) * (b - bm) for r, b in zip(returns, benchmark, strict=True)) / variance if variance > 0 else None
    captures = {}
    for label, upward in [('upside_capture', True), ('downside_capture', False)]:
        pairs = [(r, b) for r, b in zip(returns, benchmark, strict=True) if (b > 0 if upward else b < 0)]
        denominator = mean(b for _, b in pairs) if pairs else 0
        captures[label] = mean(r for r, _ in pairs) / denominator if denominator != 0 else None
    return base | {'Ulcer_Index_fraction': math.sqrt(mean(d * d for d in drawdowns)),
        'annualized_gross_turnover': sum(float(d.turnover) for d in result.days) * 252 / len(result.days),
        'cash_fraction_mean': mean(float(d.cash / d.nav) for d in result.days),
        'market_beta_to_SPY': beta, **captures, 'capture_definition': 'CONDITIONAL_ARITHMETIC_DAILY_MEAN_RATIO',
        'trade_count': len(result.trades), 'exposure_days': sum(d.exposure > 0 for d in result.days),
        'dependent_20_session_blocks_floor': len(result.days) // 20,
        'effective_independent_sample_size': None,
        'missing_data_fraction': 0, 'missing_data_semantics': 'STRICT_REPLAY_REJECTS_MISSING_REQUIRED_SESSIONS',
        'risk_adjusted_alpha_claim': False}
