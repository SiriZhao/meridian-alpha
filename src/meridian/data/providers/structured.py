"""Structured numerical providers; none of these values originate from an LLM."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from meridian.data.models import (
    DataCategory,
    EvidenceRecord,
    ResearchDataRequirement,
    SourceType,
    ValidationStatus,
)
from meridian.data.providers.base import RetrievalProviderError
from meridian.fundamentals import SECCompanyFactsNumericProvider, certified_company_snapshot
from meridian.historical import (
    HistoricalBarSeries,
    HistoricalProviderError,
    HistoricalProviderMalformed,
)


def _lookback_start(as_of: datetime, lookback: str | None) -> date:
    days = {
        "30d": 45,
        "60d": 90,
        "6m": 220,
        "1y": 380,
        "2y": 760,
    }.get((lookback or "1y").lower(), 380)
    return as_of.date() - timedelta(days=days)


class HistoricalSeriesRetrievalProvider:
    """Adapt an existing typed OHLCV provider to research evidence."""

    def __init__(self, provider: Any, *, provider_name: str | None = None) -> None:
        self.provider = provider
        self.provider_name = provider_name or str(provider.provider_name)

    def supports(self, requirement: ResearchDataRequirement) -> bool:
        return requirement.category in {
            DataCategory.PRICE_HISTORY,
            DataCategory.VOLUME_HISTORY,
            DataCategory.BENCHMARK,
        } and requirement.field in {"daily_ohlcv_1y", "daily_ohlcv", "benchmark_ohlcv_1y"}

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        try:
            series: HistoricalBarSeries = self.provider.get_series(
                requirement.symbol,
                _lookback_start(as_of, requirement.lookback),
                as_of.date(),
                as_of=as_of,
                live=True,
            )
        except HistoricalProviderMalformed as error:
            raise RetrievalProviderError(
                f"{self.provider_name.upper()}_MALFORMED", retryable=False
            ) from error
        except (HistoricalProviderError, OSError, TimeoutError) as error:
            code = str(error) if str(error).isupper() else f"{self.provider_name.upper()}_UNAVAILABLE"
            raise RetrievalProviderError(code, retryable=True) from error
        except ValueError as error:
            raise RetrievalProviderError(
                f"{self.provider_name.upper()}_INVALID_DATA", retryable=False
            ) from error
        bars = [
            {
                "session": bar.session.isoformat(),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "observed_at": bar.observed_at.isoformat(),
            }
            for bar in series.bars
            if bar.observed_at <= as_of
        ]
        if len(bars) < 15:
            raise RetrievalProviderError(
                f"{self.provider_name.upper()}_INSUFFICIENT_HISTORY", retryable=False
            )
        latest = datetime.fromisoformat(str(bars[-1]["observed_at"]))
        return (
            EvidenceRecord(
                requirement_key=requirement.key,
                field=requirement.field,
                category=requirement.category,
                value=bars,
                unit="OHLCV",
                symbol=requirement.symbol,
                timestamp=latest,
                as_of=as_of,
                source=series.provider,
                source_type=SourceType.STRUCTURED_PROVIDER,
                retrieved_at=datetime.now(UTC),
                provider=self.provider_name,
                confidence=Decimal("0.85"),
                is_estimate=False,
                raw_reference=series.content_hash or series.stable_hash,
                validation_status=ValidationStatus.PASS,
            ),
        )


class SecFundamentalRetrievalProvider:
    """Official SEC numerical observations, bounded to facts filed by the cutoff."""

    provider_name = "sec-companyfacts"

    def __init__(self, provider: SECCompanyFactsNumericProvider | None = None) -> None:
        self.provider = provider or SECCompanyFactsNumericProvider()

    def supports(self, requirement: ResearchDataRequirement) -> bool:
        return requirement.category in {
            DataCategory.FUNDAMENTALS,
            DataCategory.VALUATION,
            DataCategory.EARNINGS,
        } and requirement.field in {"latest_fundamentals", "recent_earnings"}

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        try:
            _, snapshot = certified_company_snapshot(requirement.symbol, as_of, provider=self.provider)
        except (OSError, ValueError) as error:
            raise RetrievalProviderError("SEC_COMPANYFACTS_UNAVAILABLE", retryable=True) from error
        selected = snapshot.facts
        if not selected or snapshot.latest_accepted_at is None:
            raise RetrievalProviderError("CERTIFIED_FUNDAMENTAL_DATA_MISSING")
        value = [item.model_dump(mode="json") for item in selected]
        source_uri = selected[-1].source_uri
        timestamp = snapshot.latest_accepted_at
        return (
            EvidenceRecord(
                requirement_key=requirement.key,
                field=requirement.field,
                category=requirement.category,
                value=value,
                unit="MIXED_SEC_UNITS",
                symbol=requirement.symbol,
                timestamp=timestamp,
                as_of=as_of,
                source=source_uri,
                source_type=SourceType.OFFICIAL_PRIMARY,
                retrieved_at=datetime.now(UTC),
                provider=self.provider_name,
                confidence=Decimal("0.90"),
                raw_reference=selected[-1].source_hash or source_uri,
                validation_status=ValidationStatus.PASS,
            ),
        )


class YahooMacroRetrievalProvider:
    """Small structured public macro lane for VIX and 10Y Treasury proxies."""

    provider_name = "yahoo-macro"
    _symbols = {"vix": "%5EVIX", "treasury_10y": "%5ETNX"}

    def __init__(self, *, opener: Callable[..., Any] = urlopen, timeout_seconds: float = 8.0) -> None:
        self.opener = opener
        self.timeout_seconds = timeout_seconds

    def supports(self, requirement: ResearchDataRequirement) -> bool:
        return requirement.category in {DataCategory.MACRO, DataCategory.RATES} and requirement.field in self._symbols

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        provider_symbol = self._symbols[requirement.field]
        query = urlencode({"range": "5d", "interval": "1d"})
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}?{query}"
        try:
            response = self.opener(
                Request(url, headers={"User-Agent": "MeridianAlpha/0.1 research-data"}),
                timeout=self.timeout_seconds,
            )
            document = json.loads(response.read().decode("utf-8"))
            result = document["chart"]["result"][0]
            pairs = [
                (timestamp, close)
                for timestamp, close in zip(
                    result["timestamp"], result["indicators"]["quote"][0]["close"], strict=False
                )
                if close is not None and datetime.fromtimestamp(timestamp, tz=UTC) <= as_of
            ]
            epoch, value = pairs[-1]
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as error:
            raise RetrievalProviderError("MACRO_DATA_MISSING", retryable=True) from error
        timestamp = datetime.fromtimestamp(epoch, tz=UTC)
        return (
            EvidenceRecord(
                requirement_key=requirement.key,
                field=requirement.field,
                category=requirement.category,
                value=str(Decimal(str(value))),
                unit="INDEX" if requirement.field == "vix" else "PERCENT",
                symbol=requirement.symbol,
                timestamp=timestamp,
                as_of=as_of,
                source=url,
                source_type=SourceType.STRUCTURED_PROVIDER,
                retrieved_at=datetime.now(UTC),
                provider=self.provider_name,
                confidence=Decimal("0.75"),
                raw_reference=url,
                validation_status=ValidationStatus.PASS,
            ),
        )
