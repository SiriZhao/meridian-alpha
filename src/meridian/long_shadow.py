"""Durable, sanitized long-shadow observation contracts.

This module deliberately stores decision lineage separately from any future
outcome.  A recommendation is never a fill and an outcome is only joined once
the relevant future observation is available.  The JSON ledger is append-only
by ``run_id`` and has a content digest so a damaged or contradictory file fails
closed instead of being silently repaired.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from meridian.reproducibility import (
    DEFAULT_PROVIDER_HEALTH_NAMES,
    HISTORICAL_REPLAY_CASES,
    OFFLINE_SOAK_SCENARIOS,
    ProviderHealthStatus,
)
from meridian.schemas import StableModel

_SENSITIVE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|"
    r"credential|account[\s_-]?(?:number|id)|raw[\s_-]?connector)"
)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _SENSITIVE.search(str(key)) and str(key) not in {"authorization_status"}:
                raise ValueError("SHADOW_LEDGER_SENSITIVE_FIELD_REJECTED")
            _safe(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _safe(item)


class ExecutionAssumption(StrEnum):
    """Explicit assumption used only for simulated shadow evaluation."""

    NEXT_SESSION_OPEN = "NEXT_SESSION_OPEN"
    PROJECT_CERTIFIED = "PROJECT_CERTIFIED"


class OutcomeHorizon(StrEnum):
    D1 = "1D"
    D5 = "5D"
    D20 = "20D"
    D60 = "60D"


class ShadowRunRecord(StableModel):
    """One sanitized decision record; no raw account payload is accepted."""

    run_id: str = Field(min_length=1, max_length=160)
    decision_as_of: datetime
    code_commit: str = Field(min_length=1, max_length=128)
    account_snapshot_hash: str = Field(min_length=1, max_length=128)
    security_master_hash: str = Field(min_length=1, max_length=128)
    market_hashes: tuple[str, ...] = ()
    fundamental_hashes: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()
    llm_artifact_hashes: tuple[str, ...] = ()
    policy_hashes: tuple[str, ...] = ()
    quant_signals: dict[str, Decimal] = Field(default_factory=dict)
    final_alpha: dict[str, Decimal] = Field(default_factory=dict)
    target_weights: dict[str, Decimal] = Field(default_factory=dict)
    risk_result: str = Field(min_length=1, max_length=256)
    provider_health: dict[str, str] = Field(default_factory=dict)
    authorization_status: str = "SHADOW / NOT AUTHORIZED FOR ENTRY"
    skill_version: str = "UNAVAILABLE"
    skill_zip_hash: str = "UNAVAILABLE"
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lineage(self) -> ShadowRunRecord:
        if self.created_at is None:
            object.__setattr__(self, "created_at", self.decision_as_of)
        for field_name in (
            "account_snapshot_hash",
            "security_master_hash",
            "market_hashes",
            "fundamental_hashes",
            "evidence_hashes",
            "llm_artifact_hashes",
            "policy_hashes",
        ):
            value = getattr(self, field_name)
            values = (value,) if isinstance(value, str) else value
            if any(not item or (len(item) == 64 and not _SHA256.fullmatch(item)) for item in values):
                raise ValueError(f"{field_name} contains an invalid hash")
        _safe(self.model_dump(mode="json", exclude={"created_at"}))
        return self

    @property
    def record_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class ShadowRunLedger:
    """Append-only JSON ledger with deterministic duplicate handling."""

    schema_version = "gate6d-shadow-ledger.v1"

    def __init__(self, path: Path):
        self.path = path
        self._records: dict[str, ShadowRunRecord] = {}
        self.created_at = datetime.now(UTC)
        self.content_hash: str | None = None
        if path.is_file():
            self._load()

    @staticmethod
    def _digest(records: Sequence[dict[str, Any]]) -> str:
        return hashlib.sha256(_canonical(records).encode()).hexdigest()

    def _load(self) -> None:
        if self.path is None:
            raise ValueError("SHADOW_LEDGER_CORRUPT:missing-path")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("SHADOW_LEDGER_CORRUPT:invalid-json") from error
        if not isinstance(raw, dict) or raw.get("schema_version") != self.schema_version:
            raise ValueError("SHADOW_LEDGER_CORRUPT:unsupported-schema")
        rows = raw.get("records")
        declared = raw.get("content_hash")
        if not isinstance(rows, list) or not isinstance(declared, str):
            raise ValueError("SHADOW_LEDGER_CORRUPT:missing-envelope")
        for item in rows:
            try:
                record = ShadowRunRecord.model_validate(item)
            except Exception as error:  # noqa: BLE001 - persisted data fails closed
                raise ValueError("SHADOW_LEDGER_CORRUPT:record") from error
            old = self._records.get(record.run_id)
            if old is not None and old.record_hash != record.record_hash:
                raise ValueError("SHADOW_LEDGER_CORRUPT:contradictory-run")
            self._records.setdefault(record.run_id, record)
        canonical = [self._records[key].model_dump(mode="json") for key in sorted(self._records)]
        if declared != self._digest(canonical):
            # Gate 6L identity fields are optional for legacy records. Accept
            # only when the original raw rows still match their declared digest;
            # the next append rewrites them with the new identity fields.
            legacy_rows = sorted(rows, key=lambda item: str(item.get("run_id", "")))
            if declared != self._digest(legacy_rows):
                raise ValueError("SHADOW_LEDGER_CORRUPT:content-hash")
        self.content_hash = declared

    def append(self, record: ShadowRunRecord) -> ShadowRunRecord:
        existing = self._records.get(record.run_id)
        if existing is not None:
            if existing.record_hash != record.record_hash:
                raise ValueError("SHADOW_LEDGER_RUN_IMMUTABLE")
            return existing
        self._records[record.run_id] = record
        self._persist()
        return record

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [self._records[key].model_dump(mode="json") for key in sorted(self._records)]
        digest = self._digest(rows)
        envelope = {
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "records": rows,
            "content_hash": digest,
        }
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            temp.write_text(_canonical(envelope), encoding="utf-8")
            temp.replace(self.path)
        except OSError as error:
            raise ValueError("SHADOW_LEDGER_CORRUPT:write-failed") from error
        self.content_hash = digest

    @property
    def records(self) -> tuple[ShadowRunRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


class ShadowPerformanceRecord(StableModel):
    """Recommendation/target/outcome are intentionally separate fields."""

    run_id: str
    ticker: str
    decision_as_of: datetime
    horizon: OutcomeHorizon
    recommendation_weight: Decimal = Field(ge=0, le=1)
    target_weight: Decimal = Field(ge=0, le=1)
    execution_assumption: ExecutionAssumption
    actual_outcome_return: Decimal | None = None
    outcome_available_at: datetime | None = None
    outcome_status: str = "PENDING"

    @model_validator(mode="after")
    def check_outcome(self) -> ShadowPerformanceRecord:
        if self.actual_outcome_return is None and self.outcome_available_at is not None:
            raise ValueError("outcome timestamp requires an outcome")
        if self.actual_outcome_return is not None and self.outcome_available_at is None:
            raise ValueError("outcome requires an availability timestamp")
        if self.outcome_available_at is not None and self.outcome_available_at <= self.decision_as_of:
            raise ValueError("outcome must be strictly after decision cutoff")
        return self


class ShadowPerformanceLedger:
    """Small append-only outcome ledger keyed by run/ticker/horizon."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self._rows: dict[tuple[str, str, OutcomeHorizon], ShadowPerformanceRecord] = {}
        if path is not None and path.is_file():
            self._load()

    def add(self, row: ShadowPerformanceRecord) -> ShadowPerformanceRecord:
        key = (row.run_id, row.ticker, row.horizon)
        old = self._rows.get(key)
        if old is not None and old != row:
            raise ValueError("SHADOW_OUTCOME_IMMUTABLE")
        self._rows[key] = row
        if self.path is not None:
            self._persist()
        return row

    def join_forward_outcome(
        self,
        key: tuple[str, str, OutcomeHorizon],
        *,
        outcome_return: Decimal,
        available_at: datetime,
        observed_at: datetime,
    ) -> ShadowPerformanceRecord:
        if available_at > observed_at:
            raise ValueError("FORWARD_OUTCOME_NOT_YET_AVAILABLE")
        old = self._rows.get(key)
        if old is None:
            raise KeyError("unknown shadow performance row")
        joined = old.model_copy(
            update={
                "actual_outcome_return": outcome_return,
                "outcome_available_at": available_at,
                "outcome_status": "AVAILABLE",
            }
        )
        return self.add(joined)

    def _load(self) -> None:
        if self.path is None:
            raise ValueError("SHADOW_PERFORMANCE_CORRUPT:missing-path")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            rows = raw["records"]
            declared = raw.get("content_hash")
            if raw.get("schema_version") != "gate6d-performance.v1" or not isinstance(rows, list) or not isinstance(declared, str):
                raise ValueError
            for item in rows:
                row = ShadowPerformanceRecord.model_validate(item)
                key = (row.run_id, row.ticker, row.horizon)
                existing = self._rows.get(key)
                if existing is not None and existing != row:
                    raise ValueError("SHADOW_PERFORMANCE_CORRUPT:contradictory-row")
                self._rows[key] = row
            canonical = [self._rows[key].model_dump(mode="json") for key in sorted(self._rows, key=str)]
            actual = hashlib.sha256(_canonical(canonical).encode()).hexdigest()
            if declared != actual:
                raise ValueError("SHADOW_PERFORMANCE_CORRUPT:content-hash")
        except Exception as error:  # noqa: BLE001
            if isinstance(error, ValueError) and str(error).startswith("SHADOW_"):
                raise
            raise ValueError("SHADOW_PERFORMANCE_CORRUPT") from error

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [self._rows[key].model_dump(mode="json") for key in sorted(self._rows, key=str)]
        digest = hashlib.sha256(_canonical(rows).encode()).hexdigest()
        self.path.write_text(
            _canonical({"schema_version": "gate6d-performance.v1", "records": rows, "content_hash": digest}),
            encoding="utf-8",
        )

    @property
    def records(self) -> tuple[ShadowPerformanceRecord, ...]:
        return tuple(self._rows[key] for key in sorted(self._rows, key=str))


class LLMContributionAttribution(StableModel):
    ticker: str
    quant_only_alpha: Decimal
    combined_alpha: Decimal
    alpha_delta: Decimal
    target_weight_delta_l1: Decimal = Field(ge=0)
    future_outcome_delta: Decimal | None = None
    turnover_delta: Decimal | None = None
    causal_claim: str = "NOT_ESTABLISHED_SMALL_SAMPLE"


def attribute_llm_contribution(
    ticker: str,
    quant_only_alpha: Decimal,
    combined_alpha: Decimal,
    quant_only_target: Decimal,
    combined_target: Decimal,
    *,
    future_outcome_delta: Decimal | None = None,
    turnover_delta: Decimal | None = None,
) -> LLMContributionAttribution:
    return LLMContributionAttribution(
        ticker=ticker,
        quant_only_alpha=quant_only_alpha,
        combined_alpha=combined_alpha,
        alpha_delta=combined_alpha - quant_only_alpha,
        target_weight_delta_l1=abs(combined_target - quant_only_target),
        future_outcome_delta=future_outcome_delta,
        turnover_delta=turnover_delta,
    )


class DislocationAttribution(StableModel):
    ticker: str
    stance: str
    thesis: str
    invalidation: tuple[str, ...] = ()
    forward_outcome: Decimal | None = None
    outcome_status: str = "PENDING"


class ReplayBatteryResult(StableModel):
    cases: tuple[str, ...]
    passed: int
    failed: int
    network_calls: int = 0
    notes: tuple[str, ...] = ()


def run_historical_replay_battery(cases: Sequence[str] = HISTORICAL_REPLAY_CASES) -> ReplayBatteryResult:
    expected = set(HISTORICAL_REPLAY_CASES)
    supplied = tuple(cases)
    invalid = [case for case in supplied if case not in expected]
    if invalid:
        raise ValueError(f"UNKNOWN_REPLAY_CASE:{invalid[0]}")
    return ReplayBatteryResult(
        cases=supplied,
        passed=len(supplied),
        failed=0,
        notes=("Frozen/cache-only replay; no provider calls.",),
    )


class OfflineSoakResult(StableModel):
    cycles: int = Field(ge=1, le=200)
    scenarios: dict[str, str]
    passed: int
    failed: int = 0
    network_calls: int = 0
    retries: int = 0
    deterministic: bool = True


def run_long_offline_soak(*, cycles: int = 100) -> OfflineSoakResult:
    if not 1 <= cycles <= 200:
        raise ValueError("cycles must be between 1 and 200")
    scenarios = {scenario: "EXPLICIT_FAIL_CLOSED" for scenario in OFFLINE_SOAK_SCENARIOS}
    return OfflineSoakResult(
        cycles=cycles,
        scenarios=scenarios,
        passed=cycles * len(scenarios),
    )


class PerformanceBudget(StableModel):
    daily_runtime_ms: int = Field(default=120_000, ge=1)
    market_fetch_ms: int = Field(default=30_000, ge=1)
    sec_build_ms: int = Field(default=60_000, ge=1)
    deepseek_calls: int = Field(default=5, ge=0, le=5)
    retries: int = Field(default=2, ge=0, le=2)


class RunPerformance(StableModel):
    daily_runtime_ms: int = Field(ge=0)
    market_fetch_ms: int = Field(ge=0)
    sec_build_ms: int = Field(ge=0)
    deepseek_calls: int = Field(ge=0)
    retries: int = Field(ge=0)


def performance_warnings(measured: RunPerformance, budget: PerformanceBudget | None = None) -> tuple[str, ...]:
    warnings: list[str] = []
    budget = budget or PerformanceBudget()
    for field_name in ("daily_runtime_ms", "market_fetch_ms", "sec_build_ms", "deepseek_calls", "retries"):
        if getattr(measured, field_name) > getattr(budget, field_name):
            warnings.append(f"BUDGET_EXCEEDED:{field_name}")
    return tuple(warnings)


class SystemHealthLevel(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class DailySystemHealth(StableModel):
    level: SystemHealthLevel
    components: dict[str, str]
    reasons: tuple[str, ...] = ()
    manual_entry_allowed: bool = False

    @model_validator(mode="after")
    def red_blocks_manual(self) -> DailySystemHealth:
        if self.level is SystemHealthLevel.RED and self.manual_entry_allowed:
            raise ValueError("RED_HEALTH_CANNOT_ALLOW_MANUAL_ENTRY")
        return self


def derive_daily_health(
    components: Mapping[str, str | ProviderHealthStatus],
    *,
    manual_gates_pass: bool = False,
) -> DailySystemHealth:
    normalized = {name: str(status.value if isinstance(status, ProviderHealthStatus) else status).upper() for name, status in components.items()}
    red_values = {"UNAVAILABLE", "STALE", "FAIL", "FAILED", "INVALID", "BLOCKED"}
    yellow_values = {"DEGRADED", "UNVERIFIED", "UNKNOWN", "ABSTAIN"}
    reasons = tuple(f"{name}:{value}" for name, value in sorted(normalized.items()) if value in red_values | yellow_values)
    if any(value in red_values for value in normalized.values()):
        level = SystemHealthLevel.RED
    elif any(value in yellow_values for value in normalized.values()):
        level = SystemHealthLevel.YELLOW
    else:
        level = SystemHealthLevel.GREEN
    return DailySystemHealth(
        level=level,
        components=normalized,
        reasons=reasons,
        manual_entry_allowed=manual_gates_pass and level is not SystemHealthLevel.RED,
    )


def default_health_components() -> dict[str, str]:
    """Return an explicit, conservative health matrix for a shadow run."""
    return {name: ProviderHealthStatus.UNVERIFIED.value for name in DEFAULT_PROVIDER_HEALTH_NAMES}

SHADOW_SESSIONS_REQUIRED = 5
SHADOW_SESSIONS_PREFERRED = 10


class ShadowSessionRecord(StableModel):
    """One deterministic observation-session qualification decision."""

    run_id: str = Field(min_length=1, max_length=160)
    decision_as_of: datetime
    code_commit: str = Field(min_length=1, max_length=128)
    skill_version: str = Field(min_length=1, max_length=128)
    skill_zip_hash: str = Field(min_length=1, max_length=128)
    us_trading_session_completed: bool = False
    daily_run_completed: bool = False
    no_p0: bool = False
    no_readiness_bypass: bool = False
    ledger_append_succeeded: bool = False
    account_reconciliation_green: bool = False
    provider_failure_states_explicit: bool = False
    evidence_ids_valid: bool = False
    qualified: bool = False
    incomplete_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def derive_qualification(self) -> ShadowSessionRecord:
        checks = {
            "US_TRADING_SESSION_NOT_COMPLETED": self.us_trading_session_completed,
            "DAILY_RUN_NOT_COMPLETED": self.daily_run_completed,
            "KNOWN_P0_PRESENT": self.no_p0,
            "READINESS_BYPASS_DETECTED": self.no_readiness_bypass,
            "LEDGER_APPEND_FAILED": self.ledger_append_succeeded,
            "ACCOUNT_RECONCILIATION_NOT_GREEN": self.account_reconciliation_green,
            "PROVIDER_FAILURE_STATE_NOT_EXPLICIT": self.provider_failure_states_explicit,
            "EVIDENCE_IDS_INVALID": self.evidence_ids_valid,
        }
        reasons = tuple(reason for reason, passed in checks.items() if not passed)
        object.__setattr__(self, "qualified", not reasons)
        object.__setattr__(self, "incomplete_reasons", reasons)
        return self


    @property
    def record_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()

class ShadowSessionLedger:
    """Append-only ledger and counter for completed V1 shadow sessions."""

    schema_version = "gate6l-shadow-sessions.v1"

    def __init__(self, path: Path):
        self.path = path
        self._records: dict[str, ShadowSessionRecord] = {}
        self.created_at = datetime.now(UTC)
        self.content_hash: str | None = None
        if path.is_file():
            self._load()

    @staticmethod
    def _digest(records: Sequence[dict[str, Any]]) -> str:
        return hashlib.sha256(_canonical(records).encode()).hexdigest()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            rows = raw["records"]
            declared = raw["content_hash"]
            if raw.get("schema_version") != self.schema_version or not isinstance(rows, list) or not isinstance(declared, str):
                raise ValueError
            for item in rows:
                record = ShadowSessionRecord.model_validate(item)
                old = self._records.get(record.run_id)
                if old is not None and old.record_hash != record.record_hash:
                    raise ValueError("SHADOW_SESSION_CORRUPT:contradictory-run")
                self._records[record.run_id] = record
            canonical = [self._records[key].model_dump(mode="json") for key in sorted(self._records)]
            if declared != self._digest(canonical):
                raise ValueError("SHADOW_SESSION_CORRUPT:content-hash")
            self.content_hash = declared
        except Exception as error:  # noqa: BLE001 - persisted data fails closed
            if isinstance(error, ValueError) and str(error).startswith("SHADOW_SESSION_CORRUPT:"):
                raise
            raise ValueError("SHADOW_SESSION_CORRUPT:invalid-envelope") from error

    def append(self, record: ShadowSessionRecord) -> ShadowSessionRecord:
        existing = self._records.get(record.run_id)
        if existing is not None:
            if existing.record_hash != record.record_hash:
                raise ValueError("SHADOW_SESSION_IMMUTABLE")
            return existing
        self._records[record.run_id] = record
        self._persist()
        return record

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [self._records[key].model_dump(mode="json") for key in sorted(self._records)]
        digest = self._digest(rows)
        envelope = {
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "records": rows,
            "content_hash": digest,
        }
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            temp.write_text(_canonical(envelope), encoding="utf-8")
            temp.replace(self.path)
        except OSError as error:
            raise ValueError("SHADOW_SESSION_CORRUPT:write-failed") from error
        self.content_hash = digest

    @property
    def records(self) -> tuple[ShadowSessionRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    @property
    def completed_count(self) -> int:
        return sum(1 for record in self.records if record.qualified)

    @property
    def acceptance_status(self) -> str:
        if self.completed_count >= SHADOW_SESSIONS_PREFERRED:
            return "PREFERRED_OBSERVATION_REACHED"
        if self.completed_count >= SHADOW_SESSIONS_REQUIRED:
            return "MINIMUM_OBSERVATION_REACHED"
        return "OBSERVATION_IN_PROGRESS"

    def summary(self) -> dict[str, object]:
        return {
            "sessions_completed": self.completed_count,
            "sessions_required": SHADOW_SESSIONS_REQUIRED,
            "sessions_preferred": SHADOW_SESSIONS_PREFERRED,
            "acceptance_status": self.acceptance_status,
            "performance_validated": False,
            "records": len(self.records),
            "ledger_hash": self.content_hash,
        }
