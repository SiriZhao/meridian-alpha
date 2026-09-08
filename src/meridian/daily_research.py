"""Canonical advisory research contracts; never a certified allocation signal."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.research import GroundedResearchResult
from meridian.research_universe import ResearchUniversePlan
from meridian.schemas import StableModel


class ResearchProviderStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_RUN = "NOT_RUN"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


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

    @model_validator(mode="after")
    def temporal_boundary(self) -> DailyResearchInput:
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
        body = self.model_dump(mode="json", exclude={"parent_run_id", "mode"})
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
        for item in self.results:
            if not item.cited_evidence_ids or set(item.cited_evidence_ids) != {expected[item.ticker]}:
                raise ValueError("RESEARCH_CITATION_INVALID")


class ResearchDecisionContext(StableModel):
    research_run_id: str
    parent_run_id: str
    input_hash: str
    analysis_cutoff: AwareDatetime
    status: ResearchProviderStatus
    authority: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    output: DailyResearchOutput | None = None

    @model_validator(mode="after")
    def available_requires_output(self) -> ResearchDecisionContext:
        if (self.status is ResearchProviderStatus.AVAILABLE) != (self.output is not None):
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
    provenance: Literal["NONE", "LIVE_HTTP", "FIXTURE", "REPLAY"] = "NONE"
    error_code: str | None = None
    next_action: str


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
