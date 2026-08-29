"""Project-owned fundamentals, news and macro evidence foundations.

The public adapters are intentionally conservative: provider responses are
normalized into Meridian EvidenceItems, publication/known-at timestamps are
kept separate from period dates, and missing vintage semantics remains
unverified.  Offline replay providers are used by the shadow daily fixture.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from meridian.evidence import ProviderCapabilities
from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus, StableModel


class EvidencePITCertification(StrEnum):
    CERTIFIED_HISTORICAL_PIT = "CERTIFIED_HISTORICAL_PIT"
    VERIFIED_LIVE_AS_OF = "VERIFIED_LIVE_AS_OF"
    UNVERIFIED = "UNVERIFIED"
    SYNTHETIC = "SYNTHETIC"
    REPLAY_UNSAFE = "REPLAY_UNSAFE"


class FundamentalObservation(StableModel):
    canonical_asset_id: str
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    filing_id: str = Field(min_length=1, max_length=256)
    filing_type: str = Field(min_length=1, max_length=64)
    period_end: date
    value: Decimal
    units: str = Field(min_length=1, max_length=64)
    publication_at: datetime | None = None
    available_at: datetime | None = None
    retrieved_at: datetime
    source: str = Field(min_length=1, max_length=256)
    uri: str | None = None
    point_in_time_status: EvidencePITCertification = EvidencePITCertification.UNVERIFIED

    @model_validator(mode="after")
    def validate_timestamps(self) -> FundamentalObservation:
        for name, value in (("publication_at", self.publication_at), ("available_at", self.available_at), ("retrieved_at", self.retrieved_at)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.available_at is not None and self.available_at > self.retrieved_at:
            raise ValueError("available_at must not exceed retrieved_at")
        if self.publication_at is not None and self.available_at is not None and self.publication_at > self.available_at:
            raise ValueError("publication_at must not exceed available_at")
        if self.point_in_time_status is EvidencePITCertification.CERTIFIED_HISTORICAL_PIT and self.available_at is None:
            raise ValueError("historical fundamental PIT requires available_at")
        return self

    def to_evidence_item(self) -> EvidenceItem:
        if self.available_at is None:
            raise ValueError("fundamental observation lacks authoritative available_at")
        return EvidenceItem(
            ticker=self.ticker,
            provider="sec-edgar" if self.source.startswith("SEC:") else self.source,
            source=self.source,
            published_at=self.publication_at,
            observed_at=self.available_at,
            available_at=self.available_at,
            retrieved_at=self.retrieved_at,
            title=f"{self.filing_type} {self.filing_id}",
            uri=self.uri,
            document_id=self.filing_id,
            evidence_type="fundamental",
            summary=f"{self.filing_type} {self.units} observation for period ending {self.period_end.isoformat()}",
            point_in_time_status=EvidencePointInTimeStatus(self.point_in_time_status.value),
        )


class NewsObservation(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    headline: str = Field(min_length=1, max_length=1000)
    source: str = Field(min_length=1, max_length=256)
    document_id: str = Field(min_length=1, max_length=256)
    published_at: datetime
    available_at: datetime
    retrieved_at: datetime
    uri: str | None = None
    entity_links: tuple[str, ...] = ()
    content_hash: str | None = None
    point_in_time_status: EvidencePITCertification = EvidencePITCertification.UNVERIFIED

    @model_validator(mode="after")
    def validate_news(self) -> NewsObservation:
        for name, value in (("published_at", self.published_at), ("available_at", self.available_at), ("retrieved_at", self.retrieved_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.published_at > self.available_at:
            raise ValueError("published_at must not exceed available_at")
        if self.available_at > self.retrieved_at:
            raise ValueError("available_at must not exceed retrieved_at")
        if self.content_hash is None:
            digest = hashlib.sha256(f"{self.source}|{self.document_id}|{self.headline}".encode()).hexdigest()
            object.__setattr__(self, "content_hash", digest)
        return self

    def to_evidence_item(self) -> EvidenceItem:
        return EvidenceItem(
            ticker=self.ticker,
            provider=self.source,
            source=self.source,
            published_at=self.published_at,
            observed_at=self.published_at,
            available_at=self.available_at,
            retrieved_at=self.retrieved_at,
            title=self.headline,
            uri=self.uri,
            document_id=self.document_id,
            content_hash=self.content_hash,
            evidence_type="news",
            summary=self.headline,
            point_in_time_status=EvidencePointInTimeStatus(self.point_in_time_status.value),
        )


class MacroObservation(StableModel):
    series_id: str = Field(min_length=1, max_length=128)
    observation_period: date
    value: Decimal
    units: str = Field(min_length=1, max_length=64)
    release_at: datetime | None = None
    available_at: datetime | None = None
    revision: str | None = None
    retrieved_at: datetime
    source: str = Field(min_length=1, max_length=256)
    point_in_time_status: EvidencePITCertification = EvidencePITCertification.UNVERIFIED

    @model_validator(mode="after")
    def validate_macro(self) -> MacroObservation:
        for name, value in (("release_at", self.release_at), ("available_at", self.available_at), ("retrieved_at", self.retrieved_at)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.available_at is not None and self.available_at > self.retrieved_at:
            raise ValueError("available_at must not exceed retrieved_at")
        if self.point_in_time_status is EvidencePITCertification.CERTIFIED_HISTORICAL_PIT and self.available_at is None:
            raise ValueError("macro historical PIT requires available_at")
        return self

    def to_evidence_item(self, ticker: str | None = None) -> EvidenceItem:
        available = self.available_at or self.retrieved_at
        return EvidenceItem(
            ticker=ticker,
            provider=self.source,
            source=self.source,
            published_at=self.release_at,
            observed_at=available,
            available_at=self.available_at,
            retrieved_at=self.retrieved_at,
            title=self.series_id,
            document_id=f"{self.series_id}:{self.observation_period.isoformat()}:{self.revision or 'initial'}",
            evidence_type="macro",
            summary=f"{self.series_id} observation for {self.observation_period.isoformat()}",
            point_in_time_status=EvidencePointInTimeStatus(self.point_in_time_status.value),
        )


class FundamentalEvidenceProvider(Protocol):
    capabilities: ProviderCapabilities

    def get_evidence(self, ticker: str, as_of: datetime) -> Sequence[EvidenceItem]: ...


class NewsEvidenceProvider(Protocol):
    capabilities: ProviderCapabilities

    def get_evidence(self, ticker: str, as_of: datetime) -> Sequence[EvidenceItem]: ...


class MacroEvidenceProvider(Protocol):
    capabilities: ProviderCapabilities

    def get_evidence(self, ticker: str, as_of: datetime) -> Sequence[EvidenceItem]: ...


class SECCompanyFactsProvider:
    """Public SEC Company Facts adapter with explicit non-PIT default semantics."""

    provider_name = "sec-edgar"
    network_capable = True

    def __init__(self, *, opener: Callable[..., Any] = urlopen, clock: Callable[[], datetime] | None = None, user_agent: str = "MeridianAlpha research contact unavailable"):
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))
        self.user_agent = user_agent
        self.capabilities = ProviderCapabilities(
            provider_name=self.provider_name,
            supports_live=True,
            supports_historical=True,
            supports_point_in_time=False,
            requires_api_key=False,
            execution_grade=False,
            research_grade=False,
        )
        self._ciks = {"AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810", "META": "0001326801", "GOOGL": "0001652044"}

    def get_evidence(self, ticker: str, as_of: datetime) -> tuple[EvidenceItem, ...]:
        cik = self._ciks.get(ticker.upper())
        if cik is None:
            raise ValueError("SEC_CIK_UNAVAILABLE")
        request = Request(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers={"User-Agent": self.user_agent},
        )
        response = self.opener(request, timeout=10)
        payload = response.read()
        data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        facts = data.get("facts", {}).get("us-gaap", {})
        revenue = facts.get("Revenues") or facts.get("SalesRevenueNet")
        if not isinstance(revenue, Mapping):
            return ()
        units = revenue.get("units", {})
        usd_rows = units.get("USD", []) if isinstance(units, Mapping) else []
        if not isinstance(usd_rows, list):
            return ()
        rows = [row for row in usd_rows if isinstance(row, Mapping) and row.get("form")]
        if not rows:
            return ()
        row = rows[-1]
        filed = row.get("filed")
        if not isinstance(filed, str):
            return ()
        available = datetime.fromisoformat(filed).replace(tzinfo=UTC)
        if available > as_of:
            return ()
        observation = FundamentalObservation(
            canonical_asset_id=f"US-EQ-{ticker.upper()}", ticker=ticker.upper(),
            filing_id=str(row.get("accn", "UNKNOWN")), filing_type=str(row.get("form", "UNKNOWN")),
            period_end=date.fromisoformat(str(row.get("end"))), value=Decimal(str(row.get("val"))), units="USD",
            publication_at=available, available_at=available, retrieved_at=self.clock(),
            source="SEC:CompanyFacts", uri=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            point_in_time_status=EvidencePITCertification.UNVERIFIED,
        )
        return (observation.to_evidence_item(),)


class _ReplayProvider:
    evidence_type = "macro"

    def __init__(self, provider_name: str, evidence_type: str):
        self.provider_name = provider_name
        self.evidence_type = evidence_type
        self.network_capable = False
        self.capabilities = ProviderCapabilities(
            provider_name=provider_name, supports_historical=True,
            supports_point_in_time=False, requires_api_key=False,
            execution_grade=False, research_grade=False,
        )

    def get_evidence(self, ticker: str, as_of: datetime) -> tuple[EvidenceItem, ...]:
        if ticker.upper() not in {"AAPL", "MSFT", "NVDA", "META", "GOOGL", "SPY", "QQQ", "SGOV", "GLD", "VIX"}:
            return ()
        return (
            EvidenceItem(
                ticker=ticker.upper(), provider=self.provider_name,
                source=f"SYNTHETIC:{self.provider_name}", observed_at=as_of,
                available_at=as_of, retrieved_at=as_of, evidence_type=self.evidence_type,
                title="SYNTHETIC - NOT LIVE DATA", summary="SYNTHETIC - NOT LIVE DATA",
                point_in_time_status=EvidencePointInTimeStatus.SYNTHETIC,
            ),
        )


class ReplayFundamentalEvidenceProvider(_ReplayProvider):
    def __init__(self) -> None:
        super().__init__("replay-fundamental", "fundamental")


class ReplayNewsEvidenceProvider(_ReplayProvider):
    def __init__(self) -> None:
        super().__init__("replay-news", "news")


class ReplayMacroEvidenceProvider(_ReplayProvider):
    def __init__(self) -> None:
        super().__init__("replay-macro", "macro")

