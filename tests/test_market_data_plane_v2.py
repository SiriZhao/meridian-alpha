from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from meridian.analytics.derived_market_features import derive_market_features
from meridian.market import Bar
from meridian.mcp_server import quant_metrics

AS_OF = datetime(2026, 9, 11, 20, tzinfo=UTC)


def _bars(*, scale: str = "1", future: bool = False) -> tuple[Bar, ...]:
    factor = Decimal(scale)
    start = AS_OF - timedelta(days=300)
    rows = []
    for offset in range(280):
        close = (Decimal("100") + Decimal(offset) / Decimal("5")) * factor
        timestamp = start + timedelta(days=offset)
        rows.append(Bar(timestamp=timestamp, open=close - Decimal("1"), high=close + Decimal("1"), low=close - Decimal("2"), close=close, volume=1_000_000 + offset))
    if future:
        rows.append(Bar(timestamp=AS_OF + timedelta(days=1), open=Decimal("1"), high=Decimal("1"), low=Decimal("1"), close=Decimal("1"), volume=1))
    return tuple(rows)


def test_v2_features_are_deterministic_bounded_and_benchmark_aware() -> None:
    asset = _bars(future=True)
    spy = _bars(scale="0.9")
    qqq = _bars(scale="1.1")
    first = derive_market_features(asset, as_of=AS_OF, benchmark_bars=spy, qqq_bars=qqq)
    second = derive_market_features(asset, as_of=AS_OF, benchmark_bars=spy, qqq_bars=qqq)
    assert first == second
    assert first["sma200"] is not None
    assert first["realized_volatility_20d"] is not None
    assert first["realized_volatility_60d"] is not None
    assert first["max_drawdown"] is not None
    assert first["relative_performance_spy_20d"] is not None
    assert first["relative_performance_qqq_60d"] is not None
    assert first["beta_60d"] is not None
    assert first["gap"] is not None
    assert first["return_1y"] is not None


def test_v2_features_leave_benchmark_values_unknown_when_unavailable() -> None:
    features = derive_market_features(_bars(), as_of=AS_OF)
    assert features["relative_performance_spy_20d"] is None
    assert features["relative_performance_qqq_20d"] is None
    assert features["beta_60d"] is None
    assert features["rolling_correlation_60d"] is None

def test_quant_metrics_exposes_only_bounded_research_view_with_benchmarks() -> None:
    def rows(items: tuple[Bar, ...]) -> list[dict[str, str | int]]:
        return [
            {"observed_at": item.timestamp.isoformat(), "open": str(item.open), "high": str(item.high),
             "low": str(item.low), "close": str(item.close), "volume": item.volume}
            for item in items
        ]

    result = quant_metrics("MSFT", rows(_bars()), AS_OF, rows(_bars(scale="0.9")), rows(_bars(scale="1.1")))
    assert result["status"] == "AVAILABLE"
    assert result["research_view"]["raw_series_omitted"] is True
    assert result["research_view"]["observation_count"] == 280
    assert "relative_performance_spy_20d" in result["metrics"]
    assert "raw_series" not in result
    assert result["execution_authority"] == "NONE"