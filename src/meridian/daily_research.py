"""Canonical advisory research contracts; never a certified allocation signal."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.research import GroundedResearchResult
from meridian.research_universe import ResearchUniversePlan
from meridian.schemas import StableModel
from meridian.temporal import ResearchTemporalContext


class ResearchProviderStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_RUN = "NOT_RUN"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NO_ACTION = "NO_ACTION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    CODEX_NOT_INSTALLED = "CODEX_NOT_INSTALLED"
    CODEX_AUTH_REQUIRED = "CODEX_AUTH_REQUIRED"
    CODEX_TIMEOUT = "CODEX_TIMEOUT"
    CODEX_RATE_LIMITED = "CODEX_RATE_LIMITED"
    CODEX_PROCESS_ERROR = "CODEX_PROCESS_ERROR"
    CODEX_SCHEMA_ERROR = "CODEX_SCHEMA_ERROR"
    CODEX_EMPTY_RESPONSE = "CODEX_EMPTY_RESPONSE"
    CODEX_OUTPUT_MISSING = "CODEX_OUTPUT_MISSING"
    CODEX_CONFIG_INVALID = "CODEX_CONFIG_INVALID"
    GPT_PLANNER_FAILED = "GPT_PLANNER_FAILED"
    DATA_RETRIEVAL_FAILED = "DATA_RETRIEVAL_FAILED"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ResearchFailureStatus(StrEnum):
    """Failure meanings; none may be mapped to HOLD or NO_ACTION."""

    VALID = "VALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class PublicResearchObservation(StableModel):
    """Outbound allowlist. No account, arbitrary evidence payload or free text."""

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    observed_at: AwareDatetime
    price: Decimal = Field(gt=0)
    daily_return: Decimal
    reference: str = Field(pattern=r"^[a-f0-9]{64}$")


class DailyResearchInput(StableModel):
    parent_run_id: str
    analysis_cutoff: AwareDatetime
    mode: Literal["LIVE", "FIXTURE", "REPLAY"]
    snapshot_reference: str
    market_reference: str
    policy_reference: str
    provider: str
    model: str
    prompt_version: Literal["public-advisory-v1"] = "public-advisory-v1"
    observations: tuple[PublicResearchObservation, ...]
    freshness_status: Literal["PASS", "BLOCKED"] = "BLOCKED"
    provider_provenance: dict[str, str] = Field(default_factory=dict)
    universe_plan: ResearchUniversePlan | None = None
    evidence_package: dict[str, Any] | None = None
    market_context: dict[str, Any] | None = None
    temporal_context: ResearchTemporalContext | None = None
    # Current account state is supplied only to the local Codex child process. It is
    # intentionally absent from request dumps, hashes, reports, replay artifacts,
    # and the persistent retrieval cache/audit trail.
    portfolio_context: dict[str, Any] | None = Field(
        default=None, exclude=True, repr=False
    )

    @model_validator(mode="after")
    def temporal_boundary(self) -> DailyResearchInput:
        if self.temporal_context is not None and self.temporal_context.information_cutoff != self.analysis_cutoff:
            raise ValueError("RESEARCH_TEMPORAL_CONTEXT_MISMATCH")
        if any(item.observed_at > self.analysis_cutoff for item in self.observations):
            raise ValueError("RESEARCH_INPUT_AFTER_CUTOFF")
        if len({item.ticker for item in self.observations}) != len(self.observations):
            raise ValueError("RESEARCH_DUPLICATE_SYMBOL")
        if self.universe_plan is not None and tuple(
            item.ticker for item in self.observations
        ) != self.universe_plan.deep_analysis_universe:
            raise ValueError("RESEARCH_UNIVERSE_PLAN_MISMATCH")
        return self

    @property
    def input_hash(self) -> str:
        # Run/mode metadata is distinct from reproducible facts and configuration.
        body = self.model_dump(
            mode="json", exclude={"parent_run_id", "mode", "portfolio_context"}
        )
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class SymbolResearch(GroundedResearchResult):
    ticker: str
    claim_kind: Literal["MODEL_INFERENCE"]
    data_limitations: tuple[str, ...] = Field(min_length=1)


class DailyResearchOutput(StableModel):
    results: tuple[SymbolResearch, ...] = Field(min_length=1)

    def validate_input(self, request: DailyResearchInput) -> None:
        expected = {item.ticker: item.reference for item in request.observations}
        if len(self.results) != len(expected) or {item.ticker for item in self.results} != set(expected):
            raise ValueError("RESEARCH_SYMBOL_COVERAGE_INVALID")
        safe_by_symbol: dict[str, set[str]] = {ticker: set() for ticker in expected}
        if request.evidence_package:
            raw_evidence = request.evidence_package.get("evidence", [])
            conflicts = request.evidence_package.get("conflicts", [])
            conflicted = {
                str(conflict.get("requirement_key"))
                for conflict in conflicts
                if isinstance(conflict, dict) and conflict.get("requirement_key")
            } if isinstance(conflicts, list) else set()
            if isinstance(raw_evidence, list):
                for evidence in raw_evidence:
                    if not isinstance(evidence, dict):
                        continue
                    identifier = evidence.get("evidence_id")
                    symbol = str(evidence.get("symbol", ""))
                    requirement_key = str(evidence.get("requirement_key", ""))
                    validation = evidence.get("validation_status")
                    if (
                        identifier
                        and validation in {"PASS", "DEGRADED"}
                        and requirement_key not in conflicted
                    ):
                        if symbol in safe_by_symbol:
                            safe_by_symbol[symbol].add(str(identifier))
                        elif symbol in {"MERIDIAN", "PORTFOLIO"}:
                            for values in safe_by_symbol.values():
                                values.add(str(identifier))
        for item in self.results:
            cited = set(item.cited_evidence_ids)
            allowed = {expected[item.ticker], *safe_by_symbol[item.ticker]}
            if not cited or expected[item.ticker] not in cited or not cited <= allowed:
                raise ValueError("RESEARCH_CITATION_INVALID")


class ResearchDecisionContext(StableModel):
    research_run_id: str
    parent_run_id: str
    input_hash: str
    analysis_cutoff: AwareDatetime
    status: ResearchProviderStatus
    failure_status: ResearchFailureStatus | None = None
    authority: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    output: DailyResearchOutput | None = None
    native_research_validated: bool = False

    @model_validator(mode="after")
    def available_requires_output(self) -> ResearchDecisionContext:
        if self.output is not None and self.native_research_validated:
            raise ValueError("RESEARCH_OUTPUT_SOURCE_AMBIGUOUS")
        if (self.status is ResearchProviderStatus.AVAILABLE) != (self.output is not None or self.native_research_validated):
            raise ValueError("RESEARCH_STATUS_OUTPUT_MISMATCH")
        return self


class ResearchStageResult(StableModel):
    context: ResearchDecisionContext
    prompt_created_at: AwareDatetime
    started_at: AwareDatetime
    finished_at: AwareDatetime
    request_sent_at: AwareDatetime | None = None
    response_received_at: AwareDatetime | None = None
    duration_seconds: float = Field(ge=0)
    attempts: int = Field(ge=0)
    provider: str
    model: str
    provenance: Literal["NONE", "CODEX_CLI", "FIXTURE", "REPLAY"] = "NONE"
    error_code: str | None = None
    next_action: str
    structured_response: dict[str, object] | None = None
    provider_diagnostics: dict[str, object] = Field(default_factory=dict)
    preparation_diagnostics: dict[str, object] = Field(default_factory=dict)


def validate_replay(request: DailyResearchInput, recorded: ResearchStageResult, *, replay_time: datetime, max_age_seconds: int) -> None:
    """No automatic cache reuse; require the exact original input and availability."""
    received = recorded.response_received_at
    if (recorded.context.input_hash != request.input_hash or received is None
            or replay_time.tzinfo is None or received > replay_time
            or (replay_time - received).total_seconds() > max_age_seconds
            or recorded.context.status is not ResearchProviderStatus.AVAILABLE
            or recorded.context.output is None):
        raise ValueError("RESEARCH_REPLAY_UNAVAILABLE_OR_STALE")
    if recorded.finished_at < received or received < recorded.started_at or replay_time < request.analysis_cutoff:
        raise ValueError("RESEARCH_REPLAY_TEMPORAL_INVALID")
    recorded.context.output.validate_input(request)
