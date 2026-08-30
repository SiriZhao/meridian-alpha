"""Replay-safe feature, run-manifest, and provider-health contracts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from meridian.schemas import StableModel

_SENSITIVE_CACHE_KEY = re.compile(r"(?i)(secret|password|token|authorization|api[_-]?key|credential)")


def _assert_safe_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SENSITIVE_CACHE_KEY.search(str(key)):
                raise ValueError("CACHE_SENSITIVE_FIELD_REJECTED")
            _assert_safe_payload(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _assert_safe_payload(item)
    elif isinstance(value, str) and _SENSITIVE_CACHE_KEY.search(value):
        raise ValueError("CACHE_SENSITIVE_VALUE_REJECTED")


class ProviderHealthStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"


class FrozenFeature(StableModel):
    asset: str
    as_of: datetime
    available_at: datetime
    features: dict[str, Decimal] = Field(min_length=1)
    source_hashes: tuple[str, ...] = Field(min_length=1)
    feature_version: str
    normalization_version: str

    @model_validator(mode="after")
    def validate_pit(self) -> FrozenFeature:
        if self.available_at > self.as_of:
            raise ValueError("feature available_at is after as_of")
        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in self.source_hashes):
            raise ValueError("feature source hashes must be SHA-256")
        if any(not value.is_finite() for value in self.features.values()):
            raise ValueError("feature values must be finite")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class AnalysisRunManifest(StableModel):
    run_id: str
    created_at: datetime
    code_commit: str
    account_snapshot_hash: str
    security_master_version: str
    market_hashes: tuple[str, ...] = ()
    fundamental_snapshot_hashes: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()
    llm_response_hashes: tuple[str, ...] = ()
    policy_hashes: tuple[str, ...] = ()
    feature_hashes: tuple[str, ...] = ()
    allocator_identity: str
    challenger_identity: str = "MODEL_UNAVAILABLE"

    @model_validator(mode="after")
    def validate_hashes(self) -> AnalysisRunManifest:
        for field_name in (
            "account_snapshot_hash",
            "market_hashes",
            "fundamental_snapshot_hashes",
            "evidence_hashes",
            "llm_response_hashes",
            "policy_hashes",
            "feature_hashes",
        ):
            value = getattr(self, field_name)
            values = (value,) if isinstance(value, str) else value
            if any(not re.fullmatch(r"[a-f0-9]{64}", item) for item in values):
                raise ValueError(f"{field_name} must contain SHA-256 hashes")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class CachedObservation(StableModel):
    """Safe durable cache envelope; only hashes and sanitized payloads belong here."""

    cache_key: str = Field(min_length=1, max_length=256)
    observation_type: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=32)
    available_at: datetime
    retrieved_at: datetime
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sensitive_payload(self) -> CachedObservation:
        _assert_safe_payload(self.payload)
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class ReplaySafeObservationCache:
    """Append-preserving local cache for review-safe provider artifacts."""

    def __init__(self, path: Path):
        self.path = path
        self._records: dict[str, CachedObservation] = {}
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("cache must contain a list")
            for item in raw:
                record = CachedObservation.model_validate(item)
                self._records[record.cache_key] = record

    def put(self, record: CachedObservation) -> CachedObservation:
        existing = self._records.get(record.cache_key)
        if existing is not None:
            if existing.available_at != record.available_at or existing.source_hash != record.source_hash:
                raise ValueError("CACHE_HISTORICAL_AVAILABLE_AT_IMMUTABLE")
            return existing
        self._records[record.cache_key] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([item.model_dump(mode="json") for item in self._records.values()], sort_keys=True),
            encoding="utf-8",
        )
        return record

    def get(self, cache_key: str) -> CachedObservation | None:
        return self._records.get(cache_key)

    @property
    def records(self) -> tuple[CachedObservation, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


class ProviderHealth(StableModel):
    provider: str
    status: ProviderHealthStatus
    checked_at: datetime
    latency_ms: Decimal | None = Field(default=None, ge=0)
    external_calls: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0, le=2)
    detail: str = ""
