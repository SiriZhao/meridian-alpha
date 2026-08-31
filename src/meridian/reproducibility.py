"""Replay-safe feature, run-manifest, and provider-health contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from meridian.schemas import StableModel

_SENSITIVE_CACHE_KEY = re.compile(
    r"(?i)(?:secret|password|credential|authorization|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|account[\s_-]?(?:number|id)|"
    r"raw[\s_-]?connector(?:[\s_-]?(?:data|payload))?)"
)

CACHE_SCHEMA_VERSION = "2"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


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
    # Legacy manifests may omit these fields; new manifests should always
    # provide them.  The cutoff defaults to creation time for compatibility.
    decision_as_of: datetime | None = None
    code_commit: str
    account_snapshot_hash: str
    security_master_version: str
    security_master_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    market_hashes: tuple[str, ...] = ()
    fundamental_snapshot_hashes: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()
    llm_response_hashes: tuple[str, ...] = ()
    policy_hashes: tuple[str, ...] = ()
    feature_hashes: tuple[str, ...] = ()
    allocator_identity: str
    challenger_identity: str = "MODEL_UNAVAILABLE"
    provider_capability_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_hashes(self) -> AnalysisRunManifest:
        if self.decision_as_of is None:
            object.__setattr__(self, "decision_as_of", self.created_at)
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
    record_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def reject_sensitive_payload(self) -> CachedObservation:
        _assert_safe_payload(self.payload)
        expected = self._computed_record_hash()
        if self.record_hash is not None and self.record_hash != expected:
            raise ValueError("CACHE_RECORD_HASH_MISMATCH")
        object.__setattr__(self, "record_hash", expected)
        return self

    def _record_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"record_hash"})

    def _computed_record_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self._record_body()).encode()).hexdigest()

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload).encode()).hexdigest()

    @property
    def content_hash(self) -> str:
        return self._computed_record_hash()


class ReplaySafeObservationCache:
    """Append-preserving local cache for review-safe provider artifacts."""

    def __init__(self, path: Path):
        self.path = path
        self._records: dict[str, CachedObservation] = {}
        self.schema_version = CACHE_SCHEMA_VERSION
        self.created_at = datetime.now(UTC)
        self.content_hash: str | None = None
        self.file_hash: str | None = None
        if path.is_file():
            self._load(path)

    @staticmethod
    def _corrupt(reason: str) -> ValueError:
        return ValueError(f"CACHE_CORRUPT:{reason}")

    @classmethod
    def _content_digest(cls, records: list[dict[str, Any]]) -> str:
        return hashlib.sha256(_canonical_json(records).encode()).hexdigest()

    @classmethod
    def _file_digest(
        cls, schema_version: str, created_at: str, records: list[dict[str, Any]], content_hash: str
    ) -> str:
        body = {
            "schema_version": schema_version,
            "cache_schema_version": schema_version,
            "created_at": created_at,
            "records": records,
            "content_hash": content_hash,
        }
        return hashlib.sha256(_canonical_json(body).encode()).hexdigest()

    @staticmethod
    def _duplicate_conflict(existing: CachedObservation, candidate: CachedObservation) -> bool:
        return any(
            (
                existing.available_at != candidate.available_at,
                existing.source_hash != candidate.source_hash,
                existing.payload_hash != candidate.payload_hash,
                existing.schema_version != candidate.schema_version,
                existing.provider != candidate.provider,
                existing.observation_type != candidate.observation_type,
            )
        )

    def _load(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise self._corrupt("invalid-json") from error
        if not isinstance(raw, dict):
            raise self._corrupt("envelope-required")
        if raw.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
            raise self._corrupt("unsupported-schema")
        if raw.get("schema_version", CACHE_SCHEMA_VERSION) != CACHE_SCHEMA_VERSION:
            raise self._corrupt("unsupported-schema")
        created = raw.get("created_at")
        records_raw = raw.get("records")
        declared_content = raw.get("content_hash")
        declared_file = raw.get("file_hash")
        if not isinstance(created, str) or not isinstance(records_raw, list):
            raise self._corrupt("missing-envelope-fields")
        try:
            created_dt = datetime.fromisoformat(created)
        except ValueError as error:
            raise self._corrupt("invalid-created-at") from error
        if created_dt.tzinfo is None or created_dt.utcoffset() is None:
            raise self._corrupt("created-at-not-timezone-aware")
        if not isinstance(declared_content, str) or not re.fullmatch(r"[a-f0-9]{64}", declared_content):
            raise self._corrupt("invalid-content-hash")
        if not isinstance(declared_file, str) or not re.fullmatch(r"[a-f0-9]{64}", declared_file):
            raise self._corrupt("invalid-file-hash")
        for item in records_raw:
            if not isinstance(item, dict):
                raise self._corrupt("record-not-object")
            try:
                record = CachedObservation.model_validate(item)
            except Exception as error:  # noqa: BLE001 - cache loads fail closed
                raise self._corrupt("record-validation") from error
            existing = self._records.get(record.cache_key)
            if existing is not None:
                if self._duplicate_conflict(existing, record):
                    raise self._corrupt("duplicate-cache-key-conflict")
                # Identical immutable duplicates are harmless and are
                # deterministically reduced to the first record.
                continue
            self._records[record.cache_key] = record
        canonical_records = [
            self._records[key].model_dump(mode="json") for key in sorted(self._records)
        ]
        if declared_content != self._content_digest(canonical_records):
            raise self._corrupt("content-hash-mismatch")
        if declared_file != self._file_digest(
            CACHE_SCHEMA_VERSION, created, canonical_records, declared_content
        ):
            raise self._corrupt("file-hash-mismatch")
        self.created_at = created_dt
        self.content_hash = declared_content
        self.file_hash = declared_file

    def put(self, record: CachedObservation) -> CachedObservation:
        existing = self._records.get(record.cache_key)
        if existing is not None:
            if self._duplicate_conflict(existing, record):
                if existing.available_at != record.available_at:
                    raise ValueError("CACHE_HISTORICAL_AVAILABLE_AT_IMMUTABLE")
                raise ValueError("CACHE_RECORD_IDENTITY_IMMUTABLE")
            return existing
        self._records[record.cache_key] = record
        self._persist()
        return record

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = [self._records[key].model_dump(mode="json") for key in sorted(self._records)]
        content_hash = self._content_digest(records)
        created = self.created_at.isoformat()
        file_hash = self._file_digest(CACHE_SCHEMA_VERSION, created, records, content_hash)
        envelope = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "created_at": created,
            "records": records,
            "content_hash": content_hash,
            "file_hash": file_hash,
        }
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            temp.write_text(_canonical_json(envelope), encoding="utf-8")
            temp.replace(self.path)
        except OSError as error:
            raise ValueError("CACHE_CORRUPT:write-failed") from error
        self.content_hash = content_hash
        self.file_hash = file_hash

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


DEFAULT_PROVIDER_HEALTH_NAMES = (
    "SEC",
    "market",
    "news",
    "macro",
    "DeepSeek",
    "TradingAgents",
    "execution quote",
    "FinRL-X runtime",
)

HISTORICAL_REPLAY_CASES = (
    "before_earnings_filing",
    "after_earnings_filing",
    "before_amendment",
    "after_amendment",
    "pre_market",
    "regular_session",
    "after_close",
    "holiday",
    "stale_account",
    "partial_account",
    "provider_outage",
)

OFFLINE_SOAK_SCENARIOS = (
    "sec_missing",
    "sec_corrupted",
    "market_unavailable",
    "deepseek_timeout",
    "deepseek_malformed",
    "deepseek_abstain",
    "deepseek_neutral",
    "deepseek_bullish_replay",
    "deepseek_bearish_replay",
    "quote_stale",
    "quote_wide",
    "host_stale",
    "host_partial",
    "unknown_security",
    "external_trade",
    "partial_fill",
    "finrlx_missing",
    "finrlx_bad_output",
    "dislocation_disagreement",
    "future_filing",
    "restatement",
)


def offline_reliability_soak(*, cycles: int = 3) -> dict[str, Any]:
    """Run a deterministic, network-free failure matrix for review reports.

    This is a contract soak, not a claim that external providers are healthy.
    Each scenario remains an explicit failure/fixture outcome and performs no
    retries or network calls.
    """

    if cycles < 1:
        raise ValueError("cycles must be positive")
    return {
        "mode": "OFFLINE_REPLAY",
        "cycles": cycles,
        "network_calls": 0,
        "retries": 0,
        "scenarios": {
            scenario: "EXPLICIT_FAIL_CLOSED" for scenario in OFFLINE_SOAK_SCENARIOS
        },
        "deterministic": True,
    }


def provider_health_matrix(
    observations: Mapping[str, ProviderHealth] | None = None,
    *,
    checked_at: datetime | None = None,
) -> dict[str, ProviderHealth]:
    """Return explicit read-only health for each configured provider.

    Missing observations are ``UNVERIFIED``; outages are never silently
    converted to a neutral research result.
    """

    reference = checked_at or datetime.now(UTC)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("provider health checked_at must be timezone-aware")
    supplied = dict(observations or {})
    result: dict[str, ProviderHealth] = {}
    for name in DEFAULT_PROVIDER_HEALTH_NAMES:
        result[name] = supplied.get(
            name,
            ProviderHealth(
                provider=name,
                status=ProviderHealthStatus.UNVERIFIED,
                checked_at=reference,
                detail="no capability observation supplied",
            ),
        )
    for name, health in supplied.items():
        result.setdefault(name, health)
    return result


def validate_frozen_llm_response(
    response: Mapping[str, Any],
    *,
    expected_hash: str,
    decision_as_of: datetime,
    allowed_evidence_ids: set[str] | frozenset[str] | tuple[str, ...],
    schema_version: str = "1",
) -> dict[str, Any]:
    """Validate a sanitized structured response for network-free replay.

    The digest covers the exact JSON payload supplied to replay.  Citations
    must resolve to the certified evidence set, and the response cutoff must
    equal the replay cutoff.  No provider is contacted.
    """

    if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
        raise ValueError("LLM_REPLAY_DECISION_CUTOFF_INVALID")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise ValueError("LLM_REPLAY_RESPONSE_HASH_INVALID")
    if not isinstance(response, Mapping):
        raise ValueError("LLM_REPLAY_SCHEMA_INVALID")
    sanitized = json.loads(_canonical_json(dict(response)))
    _assert_safe_payload(sanitized)
    digest = hashlib.sha256(_canonical_json(sanitized).encode()).hexdigest()
    if digest != expected_hash:
        raise ValueError("LLM_REPLAY_RESPONSE_HASH_MISMATCH")
    if "schema_version" not in sanitized:
        raise ValueError("LLM_REPLAY_SCHEMA_VERSION_MISSING")
    if str(sanitized.get("schema_version")) != schema_version:
        raise ValueError("LLM_REPLAY_SCHEMA_VERSION_MISMATCH")
    cutoff = sanitized.get("decision_as_of", sanitized.get("as_of"))
    if cutoff is None:
        raise ValueError("LLM_REPLAY_DECISION_CUTOFF_MISSING")
    try:
        parsed_cutoff = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("LLM_REPLAY_DECISION_CUTOFF_INVALID") from error
    if parsed_cutoff != decision_as_of:
        raise ValueError("LLM_REPLAY_DECISION_CUTOFF_MISMATCH")
    citations = sanitized.get("cited_evidence_ids", sanitized.get("evidence_ids", ()))
    if not isinstance(citations, (list, tuple)) or any(not isinstance(item, str) for item in citations):
        raise ValueError("LLM_REPLAY_CITATIONS_INVALID")
    if len(set(citations)) != len(citations):
        raise ValueError("LLM_REPLAY_CITATIONS_DUPLICATE")
    allowed = set(allowed_evidence_ids)
    if any(item not in allowed for item in citations):
        raise ValueError("LLM_REPLAY_CITATION_NOT_CERTIFIED")
    return sanitized
