from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.application import MeridianApplicationService
from meridian.cache_health import CacheHealthStatus, check_cache_health
from meridian.market_status import MarketStatus, market_status
from meridian.operational_data import (
    OperationalCache,
    OperationalReadiness,
    OperationalRefreshService,
)
from meridian.operational_market_snapshot import OperationalMarketSnapshot
from meridian.quotes import QuoteObservation, QuoteProviderTimeout
from meridian.runtime import RuntimePaths

NOW = datetime(2026, 9, 8, 14, 0, tzinfo=UTC)


class Provider:
    def __init__(self, name: str, response: QuoteObservation | Exception) -> None:
        self.provider_name = name
        self.response = response

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation:
        _ = symbol, as_of
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def observation() -> QuoteObservation:
    return QuoteObservation(
        canonical_asset_id="us:AAPL",
        canonical_symbol="AAPL",
        provider="primary",
        provider_symbol="AAPL",
        observed_at=NOW,
        available_at=NOW,
        retrieved_at=NOW,
        last=Decimal("100"),
        currency="USD",
        source="runtime-stabilization-test",
    )


def test_cache_health_probes_atomic_io_and_reports_stale_files(tmp_path: Path) -> None:
    (tmp_path / "orphan.lock").write_text("stale", encoding="utf-8")
    health = check_cache_health(tmp_path)
    assert health.status is CacheHealthStatus.DEGRADED
    assert health.readable and health.writable and health.atomic_replace
    assert health.stale_temporary_files == 1
    assert not tuple(tmp_path.glob("cache-health-*"))


def test_provider_cache_write_failure_is_degraded_not_fatal() -> None:
    class FailingCache:
        def load(self, symbol: str, provider: str):
            _ = symbol, provider
            return None

        def store(self, quote, *, provider=None) -> None:
            _ = quote, provider
            raise PermissionError("simulated cache ACL/EFS failure")

    result = OperationalRefreshService(
        Provider("primary", observation()),
        Provider("fallback", QuoteProviderTimeout()),
        cache=FailingCache(),  # type: ignore[arg-type]
    ).refresh("AAPL", analysis_time=NOW)
    assert result.selected is not None
    assert result.readiness is OperationalReadiness.OPERATIONAL_READY
    assert result.selected_lane == "PRIMARY"
    assert result.cache_status == "WRITE_FAILED"
    assert result.data_quality_mode == "DATA_DEGRADED"


def test_primary_fallback_cached_strategy_uses_fresh_cache(tmp_path: Path) -> None:
    cache = OperationalCache(tmp_path)
    warm = OperationalRefreshService(
        Provider("primary", observation()),
        Provider("fallback", QuoteProviderTimeout()),
        cache=cache,
    ).refresh("AAPL", analysis_time=NOW)
    assert warm.selected_lane == "PRIMARY"
    cached = OperationalRefreshService(
        Provider("primary", QuoteProviderTimeout()),
        Provider("fallback", QuoteProviderTimeout()),
        cache=cache,
    ).refresh("AAPL", analysis_time=NOW)
    assert cached.selected is not None
    assert cached.selected_lane == "CACHE"
    assert cached.cache_status == "HIT"
    assert cached.data_quality_mode == "DATA_DEGRADED"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 9, 8, 14, 0, tzinfo=UTC), MarketStatus.OPEN),
        (datetime(2026, 9, 8, 12, 0, tzinfo=UTC), MarketStatus.PRE_MARKET),
        (datetime(2026, 9, 8, 21, 0, tzinfo=UTC), MarketStatus.AFTER_HOURS),
        (datetime(2026, 9, 8, 7, 0, tzinfo=UTC), MarketStatus.CLOSED),
        (datetime(2026, 9, 7, 14, 0, tzinfo=UTC), MarketStatus.HOLIDAY),
    ],
)
def test_market_status_distinguishes_session_context(
    value: datetime, expected: MarketStatus
) -> None:
    assert market_status(value).status is expected


def test_canonical_daily_completes_safe_analysis_when_all_market_lanes_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import meridian.application as application_module

    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path / "runtime")})
    service = MeridianApplicationService(paths)
    service.paper_init()
    snapshot = service._paper_ledger().write_snapshot(paths.cache / "paper-input")

    class EmptyMarketService:
        def build(self, symbols, *, analysis_time: datetime, live: bool = False):
            _ = live
            requested = tuple(sorted(symbols))
            return OperationalMarketSnapshot(
                analysis_time=analysis_time,
                information_cutoff=analysis_time,
                quotes={},
                provider_health={
                    symbol: {"primary": "UNAVAILABLE", "secondary": "UNAVAILABLE"}
                    for symbol in requested
                },
                provider_probes={
                    symbol: {
                        "selection": "NONE",
                        "cache": {"status": "MISS", "hit": False},
                        "data_quality_mode": "DATA_DEGRADED",
                        "final_market_status": "BLOCKED",
                    }
                    for symbol in requested
                },
                cache={symbol: False for symbol in requested},
                conflicts={},
                missing_symbols={
                    symbol: "PRIMARY_AND_FALLBACK_UNAVAILABLE" for symbol in requested
                },
                data_quality_mode="DATA_DEGRADED",
            )

    class EmptyMarketFactory:
        @classmethod
        def from_runtime(cls, paths, *, timeout_seconds=4.0, policy=None):
            _ = paths, timeout_seconds, policy
            return EmptyMarketService()

    monkeypatch.setattr(
        application_module, "OperationalMarketSnapshotService", EmptyMarketFactory
    )
    result = service.daily(snapshot)

    assert result["status"] == "BLOCKED_STALE_MARKET"
    assert result["data_quality_mode"] == "DATA_DEGRADED"
    assert result["execution_mode"] == "SAFE_ANALYSIS"
    assert result["orders"] == []
    safe = result["safe_analysis"]
    assert isinstance(safe, dict)
    assert safe["status"] == "COMPLETED_NO_EXECUTION"
    assert safe["simulated_decision"]["action"] == "HOLD"  # type: ignore[index]
    assert result["forward_evidence"]["freeze"]["status"] == "FORWARD_NOT_FROZEN"  # type: ignore[index]
    startup = result["startup_diagnostics"]
    assert isinstance(startup, dict)
    assert set(startup) == {
        "environment",
        "cache",
        "data_provider",
        "market_status",
        "execution_mode",
    }
    report_text = Path(str(result["report_markdown"])).read_text(encoding="utf-8")
    for label in (
        "Environment:",
        "Cache:",
        "Data Provider:",
        "Market Status:",
        "Execution Mode:",
    ):
        assert label in report_text
