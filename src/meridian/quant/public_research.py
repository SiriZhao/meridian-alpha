"""Latest-vintage public adjusted-close diagnostics, not a PIT strategy replay."""
import math
from datetime import date
from statistics import mean, stdev

from meridian.quant.metrics import paired_block_interval
from meridian.quant.public_history import PublicHistoryReceipt


def exploratory_reference(receipt: PublicHistoryReceipt, benchmark: PublicHistoryReceipt,
                          start: date, end: date) -> dict[str, object]:
    receipt = PublicHistoryReceipt.model_validate(receipt.model_dump())
    benchmark = PublicHistoryReceipt.model_validate(benchmark.model_dump())
    if benchmark.symbol != 'SPY' or start >= end:
        raise ValueError('PUBLIC_BENCHMARK_OR_PERIOD_INVALID')
    rows = {r.session: r for r in receipt.observations if start <= r.session <= end}
    bm = {r.session: r for r in benchmark.observations if start <= r.session <= end}
    if set(rows) != set(bm) or len(rows) < 253:
        raise ValueError('PUBLIC_REFERENCE_ALIGNMENT_OR_WARMUP_INSUFFICIENT')
    sessions = sorted(rows)
    prices = [float(rows[s].adjusted_close) for s in sessions]
    bprices = [float(bm[s].adjusted_close) for s in sessions]
    returns = [b / a - 1 for a, b in zip(prices, prices[1:], strict=False)]
    brets = [b / a - 1 for a, b in zip(bprices, bprices[1:], strict=False)]
    if any(not math.isfinite(r) or abs(r) > .50 for r in (*returns, *brets)):
        raise ValueError('PUBLIC_EXTREME_ADJUSTMENT_OR_RETURN_REQUIRES_REVIEW')
    years = (sessions[-1] - sessions[0]).days / 365.25
    cagr = (prices[-1] / prices[0]) ** (1 / years) - 1
    vol = stdev(returns) * math.sqrt(252)
    downside = math.sqrt(mean(min(0, r) ** 2 for r in returns) * 252)
    peak, dd = prices[0], []
    for price in prices[1:]:
        peak = max(peak, price)
        dd.append(price / peak - 1)
    bm_mean, rmean = mean(brets), mean(returns)
    variance = sum((r - bm_mean) ** 2 for r in brets)
    beta = sum((r - rmean) * (b - bm_mean) for r, b in zip(returns, brets, strict=True)) / variance if variance else None
    raw = {f'momentum_{n}_sessions': prices[-1] / prices[-n - 1] - 1 for n in (21, 63, 126, 252)}
    raw.update({'momentum_12_minus_1_sessions': prices[-22] / prices[-253] - 1,
        'relative_momentum_126': prices[-1] / prices[-127] - bprices[-1] / bprices[-127],
        'distance_SMA60': prices[-1] / mean(prices[-60:]) - 1,
        'distance_SMA200': prices[-1] / mean(prices[-200:]) - 1})
    sensitivity = [{'one_way_adverse_bps_assumption': bps,
        'net_terminal_reference_return': (prices[-1] / prices[0]) * (1 - bps / 10000) / (1 + bps / 10000) - 1,
        'commission': None, 'spread_observed': None,
        'scope': 'FRACTIONAL_BUY_HOLD_ENTRY_AND_TERMINAL_EXIT_REFERENCE_NOT_LIMIT_FILLS'} for bps in (0, 5, 25, 50)]
    captures = {}
    for name, upward in [('upside_capture', True), ('downside_capture', False)]:
        selected = [(r, b) for r, b in zip(returns, brets, strict=True) if (b > 0 if upward else b < 0)]
        captures[name] = mean(r for r, _ in selected) / mean(b for _, b in selected) if selected else None
    return {'version': 'public-reference-diagnostics.v23', 'symbol': receipt.symbol,
        'evidence_level': receipt.evidence_level, 'financial_oos_eligible': False,
        'source_hash': receipt.response_hash, 'benchmark_hash': benchmark.response_hash,
        'retrieved_at': receipt.retrieved_at.isoformat(), 'historical_available_at': None,
        'start': str(sessions[0]), 'end': str(sessions[-1]), 'return_intervals': len(returns),
        'CAGR_actual_calendar_years': cagr, 'annualized_volatility_252_assumption': vol,
        'Sharpe_zero_rf': rmean * 252 / vol if vol else None,
        'Sortino_zero_rf': rmean * 252 / downside if downside else None,
        'max_drawdown': min(dd), 'Calmar': cagr / abs(min(dd)) if min(dd) < 0 else None,
        'Ulcer_Index_fraction': math.sqrt(mean(d * d for d in dd)), 'beta_to_SPY': beta, **captures,
        'retrospective_factor_diagnostics': raw, 'cost_sensitivity': sensitivity,
        'paired_uncertainty': paired_block_interval(returns, brets, block=20),
        'missing_price_rows': len(receipt.missing_rows),
        'missing_volume_rows': sum(r.volume is None for r in receipt.observations),
        'limitations': ['NOT_V23_SIGNAL_OR_STRATEGY_BACKTEST', 'LATEST_VINTAGE_ADJUSTED_CLOSE_TOTAL_RETURN_PROXY',
            'ACTIONS_NOT_INDEPENDENTLY_VERIFIED', 'OBSERVED_PROVIDER_SESSION_GRID_NOT_CERTIFIED_CALENDAR',
            'NO_DELISTING_OR_HISTORICAL_UNIVERSE_PROOF', 'REFERENCE_IS_UNCONSTRAINED',
            'NO_STRATEGY_TRADE_COUNT_OR_EXPOSURE_DAYS_AVAILABLE']}
