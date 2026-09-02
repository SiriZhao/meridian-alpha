from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from meridian.operational_data import (
    FreshnessPolicy,
    OperationalCache,
    OperationalProviderStatus,
    OperationalReadiness,
    OperationalRefreshService,
    data_status,
)
from meridian.quotes import QuoteObservation, QuoteProviderMalformed, QuoteProviderTimeout

NOW = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)


class Provider:
    def __init__(self, name: str, response: QuoteObservation | Exception) -> None:
        self.provider_name, self.response = name, response

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation:
        _ = symbol, as_of
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def quote(*, price: str = "100", observed: datetime = NOW) -> QuoteObservation:
    return QuoteObservation(canonical_asset_id="us:AAPL", canonical_symbol="AAPL", provider="fixture", provider_symbol="AAPL", observed_at=observed, available_at=observed, retrieved_at=max(NOW, observed), last=Decimal(price), currency="USD", source="fixture")


def test_fresh_fallback_and_research_boundary(tmp_path: Path) -> None:
    service = OperationalRefreshService(Provider("primary", QuoteProviderTimeout()), Provider("secondary", quote()), cache=OperationalCache(tmp_path))
    snapshot = service.refresh("AAPL", analysis_time=NOW)
    assert snapshot.primary.status is OperationalProviderStatus.UNAVAILABLE
    assert snapshot.readiness is OperationalReadiness.OPERATIONAL_READY
    assert snapshot.research_readiness is OperationalReadiness.RESEARCH_BLOCKED
    assert data_status(snapshot)["certification"] == "OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH"


def test_stale_and_future_quotes_degrade() -> None:
    stale = OperationalRefreshService(Provider("primary", quote(observed=NOW - timedelta(minutes=16))), Provider("secondary", QuoteProviderTimeout()))
    assert stale.refresh("AAPL", analysis_time=NOW).readiness is OperationalReadiness.OPERATIONAL_DEGRADED
    future = OperationalRefreshService(Provider("primary", quote(observed=NOW + timedelta(seconds=1))), Provider("secondary", QuoteProviderTimeout()))
    assert future.refresh("AAPL", analysis_time=NOW).primary.status is OperationalProviderStatus.INVALID_RESPONSE


def test_disagreement_invalid_response_and_cache_corruption(tmp_path: Path) -> None:
    service = OperationalRefreshService(Provider("primary", quote(price="100")), Provider("secondary", quote(price="105")), cache=OperationalCache(tmp_path), discrepancy_tolerance_percent=Decimal("0.02"))
    assert service.refresh("AAPL", analysis_time=NOW).readiness is OperationalReadiness.OPERATIONAL_DEGRADED
    invalid = OperationalRefreshService(Provider("primary", QuoteProviderMalformed()), Provider("secondary", QuoteProviderTimeout()))
    assert invalid.refresh("AAPL", analysis_time=NOW).primary.status is OperationalProviderStatus.INVALID_RESPONSE
    cache = OperationalCache(tmp_path)
    path = cache._path("AAPL", "primary")
    path.write_text("not-json", encoding="utf-8")
    assert cache.load("AAPL", "primary") is None
    assert path.with_suffix(".json.corrupt").exists()


def test_completed_session_handles_weekend_and_holiday() -> None:
    policy = FreshnessPolicy(daily_bar_max_age_sessions=3)
    assert policy.daily_bar_is_current(datetime(2026, 9, 4, tzinfo=UTC).date(), as_of=datetime(2026, 9, 7, 18, tzinfo=UTC))
    assert policy.daily_bar_is_current(datetime(2026, 7, 2, tzinfo=UTC).date(), as_of=datetime(2026, 7, 6, 18, tzinfo=UTC))
