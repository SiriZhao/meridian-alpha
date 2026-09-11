"""Validation contracts for web market evidence supplied by the outer Astra host.

This module deliberately has no network or model dependency.  Astra discovers
sources with its host browsing capability; Meridian validates compact facts.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import AwareDatetime, Field, model_validator

from meridian.schemas import StableModel


class TrustedSourceTier(StrEnum):
    TIER_A_PRIMARY = "TIER_A_PRIMARY"
    TIER_B_ESTABLISHED = "TIER_B_ESTABLISHED"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"


class CorroborationStatus(StrEnum):
    SINGLE_TIER_A = "SINGLE_TIER_A"
    TWO_INDEPENDENT_SOURCES = "TWO_INDEPENDENT_SOURCES"
    INSUFFICIENT_CORROBORATION = "INSUFFICIENT_CORROBORATION"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


class TrustedSourcePolicy(StableModel):
    tier_a_domains: tuple[str, ...] = (
        "sec.gov", "federalreserve.gov", "fred.stlouisfed.org", "treasury.gov",
        "bls.gov", "bea.gov", "nasdaq.com", "nyse.com", "cboe.com",
    )
    tier_b_domains: tuple[str, ...] = ("finance.yahoo.com", "reuters.com")
    discovery_only_domains: tuple[str, ...] = ()
    company_ir_domains: tuple[str, ...] = ()

    def classify(self, domain: str) -> TrustedSourceTier | None:
        value = domain.lower().removeprefix("www.")
        if any(value == candidate or value.endswith("." + candidate) for candidate in self.tier_a_domains):
            return TrustedSourceTier.TIER_A_PRIMARY
        if any(value == candidate or value.endswith("." + candidate) for candidate in self.tier_b_domains):
            return TrustedSourceTier.TIER_B_ESTABLISHED
        if any(value == candidate or value.endswith("." + candidate) for candidate in self.discovery_only_domains):
            return TrustedSourceTier.DISCOVERY_ONLY
        if any(value == candidate or value.endswith("." + candidate) for candidate in self.company_ir_domains):
            return TrustedSourceTier.TIER_A_PRIMARY
        return None


class TrustedWebMarketEvidence(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,31}$")
    field: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    value: Decimal
    unit: str = Field(min_length=1, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    source_name: str = Field(min_length=1, max_length=256)
    source_domain: str = Field(min_length=1, max_length=256)
    source_url: str = Field(min_length=1, max_length=2000)
    source_tier: TrustedSourceTier | None = None
    published_at: AwareDatetime | None = None
    observed_at: AwareDatetime
    retrieved_at: AwareDatetime
    known_at: AwareDatetime
    analysis_cutoff: AwareDatetime
    evidence_type: str = Field(default="SCALAR_MARKET_FACT", pattern=r"^(SCALAR_MARKET_FACT|HISTORICAL_TABLE)$")
    provenance_id: str | None = Field(default=None, max_length=128)
    corroboration_status: CorroborationStatus = CorroborationStatus.INSUFFICIENT_CORROBORATION
    quality_status: str = "PENDING_VALIDATION"
    execution_quote_grade: bool = False
    historical_rows: tuple[dict[str, object], ...] = ()

    @model_validator(mode="after")
    def validate_source_and_time(self) -> TrustedWebMarketEvidence:
        parsed = urlparse(self.source_url)
        domain = parsed.netloc.lower().split(":", 1)[0].removeprefix("www.")
        if parsed.scheme != "https" or not domain or domain != self.source_domain.lower().removeprefix("www."):
            raise ValueError("TRUSTED_WEB_SOURCE_URL_INVALID")
        if self.value.is_finite() is False:
            raise ValueError("TRUSTED_WEB_NUMERIC_VALUE_INVALID")
        if self.observed_at > self.known_at or self.known_at > self.retrieved_at or self.known_at > self.analysis_cutoff:
            raise ValueError("TRUSTED_WEB_EVIDENCE_AFTER_CUTOFF")
        if self.published_at is not None and self.published_at > self.analysis_cutoff:
            raise ValueError("TRUSTED_WEB_PUBLISHED_AFTER_CUTOFF")
        if self.execution_quote_grade:
            raise ValueError("TRUSTED_WEB_EXECUTION_GRADE_FORBIDDEN")
        if self.evidence_type == "HISTORICAL_TABLE" and not self.historical_rows:
            raise ValueError("HISTORICAL_TABLE_ROWS_REQUIRED")
        if self.evidence_type != "HISTORICAL_TABLE" and self.historical_rows:
            raise ValueError("NARRATIVE_EVIDENCE_CANNOT_CARRY_BARS")
        if self.evidence_type == "HISTORICAL_TABLE":
            required = {"observed_at", "open", "high", "low", "close", "volume"}
            if any(not required <= set(row) for row in self.historical_rows):
                raise ValueError("HISTORICAL_TABLE_ROW_MALFORMED")
        if self.provenance_id is None:
            body = f"{self.symbol}|{self.field}|{self.value}|{self.unit}|{self.source_url}|{self.observed_at.isoformat()}"
            object.__setattr__(self, "provenance_id", "E-MKT-" + hashlib.sha256(body.encode()).hexdigest()[:20].upper())
        return self


def validate_trusted_market_evidence(
    evidence: tuple[TrustedWebMarketEvidence, ...], *, policy: TrustedSourcePolicy | None = None
) -> dict[str, Any]:
    """Classify supplied web evidence.  Conflicts are never averaged."""
    policy = policy or TrustedSourcePolicy()
    accepted: list[TrustedWebMarketEvidence] = []
    rejected: list[dict[str, str]] = []
    by_key: dict[tuple[str, str, str | None], list[TrustedWebMarketEvidence]] = {}
    currencies: dict[tuple[str, str], set[str | None]] = {}
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        tier = policy.classify(item.source_domain)
        identity = (item.provenance_id or "", item.source_url)
        if identity in seen:
            rejected.append({"provenance_id": item.provenance_id or "", "reason": "DUPLICATE_SOURCE"})
            continue
        seen.add(identity)
        if tier is None or tier is TrustedSourceTier.DISCOVERY_ONLY:
            rejected.append({"provenance_id": item.provenance_id or "", "reason": "UNTRUSTED_OR_DISCOVERY_ONLY_SOURCE"})
            continue
        accepted.append(item.model_copy(update={"source_tier": tier, "quality_status": "SOURCE_ACCEPTED"}))
        by_key.setdefault((item.symbol, item.field, item.currency), []).append(accepted[-1])
        currencies.setdefault((item.symbol, item.field), set()).add(item.currency)
    conflicts: list[dict[str, object]] = []
    insufficient: list[str] = []
    final: list[TrustedWebMarketEvidence] = []
    for (symbol, field), units in currencies.items():
        if len(units) > 1:
            conflicts.append({"symbol": symbol, "field": field, "reason": "CURRENCY_MISMATCH", "currencies": sorted(unit or "NONE" for unit in units)})
    for key, items in by_key.items():
        if len(currencies[(key[0], key[1])]) > 1:
            continue
        values = {item.value for item in items}
        if len(values) > 1:
            conflicts.append({"symbol": key[0], "field": key[1], "currency": key[2], "evidence_ids": [item.provenance_id for item in items], "values": [str(item.value) for item in items]})
            continue
        has_tier_a = any(item.source_tier is TrustedSourceTier.TIER_A_PRIMARY for item in items)
        domains = {item.source_domain.lower().removeprefix("www.") for item in items}
        if has_tier_a:
            final.extend(item.model_copy(update={"corroboration_status": CorroborationStatus.SINGLE_TIER_A, "quality_status": "ACCEPTED"}) for item in items)
        elif len(domains) >= 2:
            final.extend(item.model_copy(update={"corroboration_status": CorroborationStatus.TWO_INDEPENDENT_SOURCES, "quality_status": "ACCEPTED"}) for item in items)
        else:
            insufficient.extend(item.provenance_id or "" for item in items)
    status = "CONFLICT" if conflicts else "ACCEPTED" if final and not rejected and not insufficient else "INSUFFICIENT_CORROBORATION" if insufficient else "REJECTED"
    return {"status": status, "accepted": [item.model_dump(mode="json") for item in final], "rejected": rejected, "conflicts": conflicts, "insufficient_corroboration": insufficient, "execution_authority": "NONE"}
