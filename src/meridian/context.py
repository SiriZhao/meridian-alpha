"""Non-authorizing news, macro-vintage, and deterministic regime contracts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from meridian.schemas import StableModel


class ShadowContextStatus(StrEnum):
    UNVERIFIED_SHADOW = "UNVERIFIED_SHADOW"
    CONFIGURATION_UNAVAILABLE = "CONFIGURATION_UNAVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ShadowNewsObservation(StableModel):
    provider: str
    article_id: str = Field(min_length=1, max_length=256)
    publisher: str = Field(min_length=1, max_length=256)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    published_at: datetime
    available_at: datetime
    canonical_uri: str = Field(min_length=1, max_length=2000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ShadowContextStatus = ShadowContextStatus.UNVERIFIED_SHADOW

    @model_validator(mode="after")
    def validate_shadow_only(self) -> ShadowNewsObservation:
        if self.available_at < self.published_at:
            raise ValueError("news available_at must not precede published_at")
        if self.status is not ShadowContextStatus.UNVERIFIED_SHADOW:
            raise ValueError("generic news is shadow-only until PIT semantics are certified")
        return self


class MacroVintageObservation(StableModel):
    series_id: str = Field(min_length=1, max_length=128)
    observation_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    value: Decimal
    vintage_at: datetime
    retrieved_at: datetime
    source_uri: str = Field(min_length=1, max_length=2000)
    revision_identity: str = Field(min_length=1, max_length=256)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ShadowContextStatus = ShadowContextStatus.UNVERIFIED_SHADOW

    def available_for(self, cutoff: datetime) -> bool:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("macro cutoff must be timezone-aware")
        return self.vintage_at <= cutoff


class RegimeFeature(StableModel):
    name: str
    value: Decimal
    available_at: datetime
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ShadowContextStatus = ShadowContextStatus.UNVERIFIED_SHADOW


class MarketRegimeSnapshot(StableModel):
    as_of: datetime
    regime: str
    features: tuple[RegimeFeature, ...]
    lineage_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ShadowContextStatus = ShadowContextStatus.UNVERIFIED_SHADOW


def build_market_regime_snapshot(
    as_of: datetime, features: tuple[RegimeFeature, ...]
) -> MarketRegimeSnapshot:
    """Classify a tiny, lineage-backed shadow regime without an LLM."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("regime as_of must be timezone-aware")
    if not features:
        raise ValueError("regime requires valid lineage-backed features")
    if any(item.available_at > as_of for item in features):
        raise ValueError("regime feature is after cutoff")
    values = {item.name: item.value for item in features}
    trend = values.get("broad_index_return", Decimal("0"))
    volatility = values.get("volatility_level", Decimal("0"))
    regime = (
        "RISK_OFF"
        if trend < 0 and volatility > Decimal("25")
        else "RISK_ON"
        if trend > 0
        else "NEUTRAL"
    )
    lineage = "|".join(
        f"{item.name}:{item.source_hash}" for item in sorted(features, key=lambda value: value.name)
    )
    return MarketRegimeSnapshot(
        as_of=as_of,
        regime=regime,
        features=features,
        lineage_hash=hashlib.sha256(lineage.encode()).hexdigest(),
    )


def fred_configuration_status(api_key_present: bool) -> ShadowContextStatus:
    """A configuration check only; it never reads or returns a secret."""
    return (
        ShadowContextStatus.UNVERIFIED_SHADOW
        if api_key_present
        else ShadowContextStatus.CONFIGURATION_UNAVAILABLE
    )
