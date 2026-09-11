"""Strict requirements, provenance, provider, and quality models."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from meridian.schemas import StableModel
from meridian.trusted_web_market import TrustedWebMarketEvidence


class DataCategory(StrEnum):
    PRICE_HISTORY = "PRICE_HISTORY"
    VOLUME_HISTORY = "VOLUME_HISTORY"
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    VOLATILITY = "VOLATILITY"
    TECHNICAL = "TECHNICAL"
    FUNDAMENTALS = "FUNDAMENTALS"
    VALUATION = "VALUATION"
    EARNINGS = "EARNINGS"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"
    NEWS = "NEWS"
    MACRO = "MACRO"
    RATES = "RATES"
    BENCHMARK = "BENCHMARK"
    MARKET_REGIME = "MARKET_REGIME"
    PORTFOLIO_CONTEXT = "PORTFOLIO_CONTEXT"
    INVESTMENT_HORIZON = "INVESTMENT_HORIZON"


class RequirementStatus(StrEnum):
    MISSING = "MISSING"
    AVAILABLE = "AVAILABLE"
    RETRIEVED = "RETRIEVED"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"


class DataStatus(StrEnum):
    DATA_COMPLETE = "DATA_COMPLETE"
    DATA_DEGRADED = "DATA_DEGRADED"
    DATA_RETRIEVAL_FAILED = "DATA_RETRIEVAL_FAILED"
    NUMERICAL_DATA_MISSING = "NUMERICAL_DATA_MISSING"
    FUNDAMENTAL_DATA_MISSING = "FUNDAMENTAL_DATA_MISSING"
    NEWS_DATA_MISSING = "NEWS_DATA_MISSING"
    MACRO_DATA_MISSING = "MACRO_DATA_MISSING"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    WEB_RESEARCH_FAILED = "WEB_RESEARCH_FAILED"
    GPT_PLANNER_FAILED = "GPT_PLANNER_FAILED"
    GPT_RESEARCH_FAILED = "GPT_RESEARCH_FAILED"
    MARKET_CLOSED = "MARKET_CLOSED"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    RESEARCH_COMPLETE_EXECUTION_BLOCKED = "RESEARCH_COMPLETE_EXECUTION_BLOCKED"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


class SourceType(StrEnum):
    STRUCTURED_PROVIDER = "STRUCTURED_PROVIDER"
    OFFICIAL_PRIMARY = "OFFICIAL_PRIMARY"
    LOCAL_CACHE = "LOCAL_CACHE"
    DETERMINISTIC_DERIVED = "DETERMINISTIC_DERIVED"
    CODEX_WEB_RESEARCH = "CODEX_WEB_RESEARCH"
    POLICY = "POLICY"
    PORTFOLIO_REFERENCE = "PORTFOLIO_REFERENCE"


class DataQualityGrade(StrEnum):
    HIGH = "HIGH"
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class ResearchDataRequirement(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,31}$")
    asset_type: str = Field(min_length=1, max_length=32)
    field: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    category: DataCategory
    required: bool = True
    importance: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    lookback: str | None = Field(default=None, max_length=32)
    frequency: str | None = Field(default=None, max_length=32)
    freshness_requirement: str | None = Field(default=None, max_length=32)
    preferred_sources: tuple[str, ...] = ()
    allow_web_fallback: bool = False
    status: RequirementStatus = RequirementStatus.MISSING
    reason: str = Field(min_length=1, max_length=1000)

    @property
    def key(self) -> str:
        return f"{self.symbol}:{self.category.value}:{self.field}"


class EvidenceRecord(StableModel):
    """One accepted fact. Values without provenance cannot instantiate this model."""

    evidence_id: str | None = Field(default=None, min_length=1, max_length=128)
    requirement_key: str = Field(min_length=1, max_length=160)
    field: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    category: DataCategory
    value: Any
    unit: str = Field(min_length=1, max_length=64)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,31}$")
    timestamp: AwareDatetime
    as_of: AwareDatetime
    source: str = Field(min_length=1, max_length=512)
    source_type: SourceType
    retrieved_at: AwareDatetime
    provider: str = Field(min_length=1, max_length=128)
    confidence: Decimal = Field(ge=0, le=1)
    is_estimate: bool = False
    raw_reference: str = Field(min_length=1, max_length=2048)
    validation_status: ValidationStatus = ValidationStatus.PASS
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> EvidenceRecord:
        if self.value is None:
            raise ValueError("EVIDENCE_VALUE_MISSING")
        if self.timestamp > self.as_of:
            raise ValueError("EVIDENCE_AFTER_AS_OF")
        if self.expires_at is not None and self.expires_at < self.retrieved_at:
            raise ValueError("EVIDENCE_EXPIRY_INVALID")
        if self.source_type is SourceType.CODEX_WEB_RESEARCH and self.category not in {
            DataCategory.NEWS,
            DataCategory.EARNINGS,
            DataCategory.CORPORATE_ACTIONS,
        }:
            raise ValueError("WEB_RESEARCH_CANNOT_SUPPLY_NUMERICAL_EVIDENCE")
        if self.evidence_id is None:
            body = json.dumps(
                {
                    "key": self.requirement_key,
                    "provider": self.provider,
                    "source": self.source,
                    "raw_reference": self.raw_reference,
                    "timestamp": self.timestamp.isoformat(),
                    "value": self.value,
                },
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            )
            object.__setattr__(self, "evidence_id", "ev_" + hashlib.sha256(body.encode()).hexdigest()[:24])
        return self


class ProviderFailure(StableModel):
    provider: str
    requirement_key: str
    reason: str
    retryable: bool = False
    occurred_at: AwareDatetime
    attempt: int = Field(ge=1, le=10)


class ProviderHealth(StableModel):
    provider: str
    status: str = Field(pattern=r"^(HEALTHY|DEGRADED|OPEN_CIRCUIT|UNKNOWN)$")
    health_score: Decimal = Field(ge=0, le=1)
    consecutive_failures: int = Field(ge=0)
    last_success: AwareDatetime | None = None


class ProviderResult(StableModel):
    provider: str
    requirement_key: str
    evidence: tuple[EvidenceRecord, ...] = ()
    failure: ProviderFailure | None = None
    health: ProviderHealth
    elapsed_ms: int = Field(ge=0)
    cache_hit: bool = False

    @model_validator(mode="after")
    def one_outcome(self) -> ProviderResult:
        if bool(self.evidence) == bool(self.failure):
            raise ValueError("PROVIDER_RESULT_REQUIRES_ONE_OUTCOME")
        return self


class SourceConflict(StableModel):
    requirement_key: str
    field: str
    symbol: str
    evidence_ids: tuple[str, ...] = Field(min_length=2)
    relative_difference: Decimal = Field(ge=0)
    tolerance: Decimal = Field(ge=0)
    status: str = "SOURCE_CONFLICT"


class DataQualityScore(StableModel):
    score: int = Field(ge=0, le=100)
    grade: DataQualityGrade
    completeness: Decimal = Field(ge=0, le=1)
    freshness: Decimal = Field(ge=0, le=1)
    source_quality: Decimal = Field(ge=0, le=1)
    cross_source_agreement: Decimal = Field(ge=0, le=1)
    timestamp_integrity: Decimal = Field(ge=0, le=1)
    coverage: Decimal = Field(ge=0, le=1)
    blocking_missing: tuple[str, ...] = ()


class ResearchEvidencePackage(StableModel):
    schema_version: str = "meridian-research-evidence.v1"
    as_of: AwareDatetime
    created_at: AwareDatetime
    status: DataStatus
    requirements: tuple[ResearchDataRequirement, ...]
    evidence: tuple[EvidenceRecord, ...]
    provider_results: tuple[ProviderResult, ...] = ()
    conflicts: tuple[SourceConflict, ...] = ()
    quality: DataQualityScore
    source_count: int = Field(ge=0)
    rounds: int = Field(default=0, ge=0, le=3)
    planner_summary: str = ""
    unresolved: tuple[str, ...] = ()
    structured_market_evidence: tuple[str, ...] = ()
    trusted_web_market_evidence: tuple[TrustedWebMarketEvidence, ...] = ()
    data_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_packet_evidence(self) -> ResearchEvidencePackage:
        if any(item.timestamp > self.as_of for item in self.evidence):
            raise ValueError("PACKET_EVIDENCE_AFTER_CUTOFF")
        if len(self.evidence_ids) != len(self.evidence):
            raise ValueError("PACKET_DUPLICATE_EVIDENCE_ID")
        if any(not set(item.evidence_ids) <= self.evidence_ids for item in self.conflicts):
            raise ValueError("PACKET_CONFLICT_EVIDENCE_UNKNOWN")
        return self

    @property
    def evidence_ids(self) -> set[str]:
        return {item.evidence_id or "" for item in self.evidence}

    @property
    def available_keys(self) -> set[str]:
        return {
            item.requirement_key
            for item in self.evidence
            if item.validation_status is not ValidationStatus.REJECTED
        }

    def compact_summary(self) -> dict[str, Any]:
        sections: dict[str, list[dict[str, Any]]] = {}
        for item in self.evidence:
            sections.setdefault(item.category.value, []).append(
                {
                    "evidence_id": item.evidence_id,
                    "field": item.field,
                    "symbol": item.symbol,
                    "value": item.value,
                    "unit": item.unit,
                    "timestamp": item.timestamp.isoformat(),
                    "source": item.source,
                    "provider": item.provider,
                    "confidence": str(item.confidence),
                    "validation_status": item.validation_status.value,
                    "is_estimate": item.is_estimate,
                }
            )
        return {
            "schema_version": self.schema_version,
            "as_of": self.as_of.isoformat(),
            "status": self.status.value,
            "quality": self.quality.model_dump(mode="json"),
            "sections": sections,
            "conflicts": [item.model_dump(mode="json") for item in self.conflicts],
            "unresolved": list(self.unresolved),
            "structured_market_evidence": list(self.structured_market_evidence),
            "trusted_web_market_evidence": [item.model_dump(mode="json") for item in self.trusted_web_market_evidence],
            "data_gaps": list(self.data_gaps),
        }

    def research_view(self) -> dict[str, Any]:
        """Return a bounded, provenance-bearing view for the reasoning runtime.

        Raw historical arrays remain available to deterministic analytics and the
        retrieval audit, but are replaced here by coverage metadata. Current
        portfolio values travel in ``ResearchPacket.portfolio_context`` only and
        are never copied into this persistable request view.
        """

        def compact_value(item: EvidenceRecord) -> Any:
            if item.category is DataCategory.PORTFOLIO_CONTEXT:
                return {
                    "in_memory_context_supplied": True,
                    "account_identifier_included": False,
                    "persistence_allowed": False,
                }
            if not isinstance(item.value, list) or item.category not in {DataCategory.PRICE_HISTORY, DataCategory.VOLUME_HISTORY, DataCategory.BENCHMARK}:
                return item.value
            sessions = [
                str(row.get("session") or row.get("observed_at"))
                for row in item.value
                if isinstance(row, dict) and (row.get("session") or row.get("observed_at"))
            ]
            return {
                "raw_series_omitted": True,
                "observation_count": len(item.value),
                "first_session": sessions[0] if sessions else None,
                "last_session": sessions[-1] if sessions else None,
                "derived_features_supplied_separately": True,
            }

        evidence = [
            {
                "evidence_id": item.evidence_id,
                "requirement_key": item.requirement_key,
                "field": item.field,
                "category": item.category.value,
                "value": compact_value(item),
                "unit": item.unit,
                "symbol": item.symbol,
                "timestamp": item.timestamp.isoformat(),
                "as_of": item.as_of.isoformat(),
                "source": item.source,
                "raw_reference": item.raw_reference,
                "source_type": item.source_type.value,
                "retrieved_at": item.retrieved_at.isoformat(),
                "provider": item.provider,
                "confidence": str(item.confidence),
                "is_estimate": item.is_estimate,
                "validation_status": item.validation_status.value,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            }
            for item in self.evidence
        ]
        return {
            "schema_version": self.schema_version,
            "as_of": self.as_of.isoformat(),
            "status": self.status.value,
            "quality": self.quality.model_dump(mode="json"),
            "requirements": [
                item.model_dump(mode="json") for item in self.requirements
            ],
            "evidence": evidence,
            "conflicts": [item.model_dump(mode="json") for item in self.conflicts],
            "source_count": self.source_count,
            "rounds": self.rounds,
            "planner_summary": self.planner_summary,
            "unresolved": list(self.unresolved),
        }


def quality_grade(score: int) -> DataQualityGrade:
    if score >= 90:
        return DataQualityGrade.HIGH
    if score >= 75:
        return DataQualityGrade.GOOD
    if score >= 60:
        return DataQualityGrade.DEGRADED
    return DataQualityGrade.INSUFFICIENT


def utc_seconds(value: datetime) -> int:
    return int(value.timestamp())
