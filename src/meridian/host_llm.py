"""Explicit Codex-host handoff artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from meridian.market_identity import canonical_market_reference
from meridian.runtime import RuntimePaths
from meridian.runtime_io import atomic_write
from meridian.schemas import StableModel


class HostJobStage(StrEnum):
    RESEARCH = "HOST_LLM_RESEARCH"
    ADVISORY = "HOST_LLM_ADVISORY"


class HostSymbolResearch(StableModel):
    """Symbol-scoped claims; market-level prose cannot substitute for these."""
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    thesis: str = Field(min_length=1, max_length=4000)
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(ge=0, le=1)
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    data_limitations: tuple[str, ...] = ()


class HostLLMJob(StableModel):
    schema_version: str = "meridian-host-llm-job.v1"
    job_id: str = Field(min_length=8, max_length=160)
    run_id: str = Field(min_length=8, max_length=160)
    stage: HostJobStage
    created_at: datetime
    prompt_version: str = "meridian-host-prompt.v1"
    market_context: dict[str, Any] = Field(default_factory=dict)
    portfolio_context: dict[str, Any] | None = None
    risk_context: dict[str, Any] = Field(default_factory=dict)
    strategy_context: dict[str, Any] = Field(default_factory=dict)
    research_questions: tuple[str, ...] = ()
    required_output_schema: dict[str, Any]
    as_of: datetime | None = None
    market_snapshot_id: str | None = None
    symbol_universe: tuple[str, ...] = ()
    quote_timestamps: dict[str, datetime] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    model_runtime_provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def market_reference_is_canonical(self) -> HostLLMJob:
        quotes = self.market_context.get("quotes")
        if isinstance(quotes, dict) and quotes and self.strategy_context.get("market_reference") != canonical_market_reference(quotes):
            raise ValueError("HOST_LLM_JOB_MARKET_REFERENCE_INVALID")
        cutoff = self.market_context.get("cutoff")
        if self.as_of is None and isinstance(cutoff, str):
            object.__setattr__(self, "as_of", datetime.fromisoformat(cutoff))
        if self.as_of is None:
            object.__setattr__(self, "as_of", self.created_at)
        if self.market_snapshot_id is None:
            reference_payload = quotes if isinstance(quotes, dict) else self.market_context
            object.__setattr__(self, "market_snapshot_id", canonical_market_reference(reference_payload))
        if not self.symbol_universe and isinstance(quotes, dict):
            object.__setattr__(self, "symbol_universe", tuple(sorted(str(item) for item in quotes)))
        if not self.quote_timestamps and isinstance(quotes, dict):
            timestamps: dict[str, datetime] = {}
            for symbol, raw in quotes.items():
                if isinstance(raw, dict) and isinstance(raw.get("timestamp"), str):
                    timestamps[str(symbol)] = datetime.fromisoformat(str(raw["timestamp"]))
            object.__setattr__(self, "quote_timestamps", timestamps)
        raw_evidence = self.market_context.get("evidence_ids")
        if not self.evidence_ids and isinstance(raw_evidence, dict):
            object.__setattr__(self, "evidence_ids", tuple(sorted(str(item) for item in raw_evidence.values())))
        if not self.model_runtime_provenance:
            object.__setattr__(
                self,
                "model_runtime_provenance",
                {"provider": "HOST_CODEX", "runtime": "CHATGPT_HOST"},
            )
        return self


class HostLLMResult(StableModel):
    schema_version: str = "meridian-host-llm-result.v1"
    job_id: str = Field(min_length=8, max_length=160)
    run_id: str = Field(min_length=8, max_length=160)
    status: str = Field(pattern=r"^OK$")
    summary: str = Field(min_length=1, max_length=8000)
    market_regime: str = Field(min_length=1, max_length=120)
    bull_case: tuple[str, ...] = ()
    base_case: tuple[str, ...] = ()
    bear_case: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    opportunities: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    evidence: tuple[str, ...] = Field(min_length=1)
    portfolio_implications: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    symbol_research: tuple[HostSymbolResearch, ...] = ()
    research_snapshot_id: str = Field(min_length=8, max_length=128)
    research_as_of: datetime
    model_runtime_provenance: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_are_present(self) -> HostLLMResult:
        if not self.job_id or not self.run_id:
            raise ValueError("HOST_LLM_RESULT_IDS_REQUIRED")
        return self


class HostHandoffError(ValueError):
    pass


def host_run_directory(paths: RuntimePaths, run_id: str) -> Path:
    directory = paths.runs / run_id / "llm"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_job(
    paths: RuntimePaths,
    *,
    run_id: str,
    stage: HostJobStage,
    market_context: dict[str, Any],
    portfolio_context: dict[str, Any] | None,
    risk_context: dict[str, Any],
    strategy_context: dict[str, Any],
    research_questions: tuple[str, ...],
    required_output_schema: dict[str, Any],
) -> tuple[HostLLMJob, Path]:
    job = HostLLMJob(
        job_id=f"job-{uuid4().hex}",
        run_id=run_id,
        stage=stage,
        created_at=datetime.now(UTC),
        market_context=market_context,
        portfolio_context=portfolio_context,
        risk_context=risk_context,
        strategy_context=strategy_context,
        research_questions=research_questions,
        required_output_schema=required_output_schema,
    )
    path = host_run_directory(paths, run_id) / f"{stage.value.lower()}.job.json"
    atomic_write(path, json.dumps(job.model_dump(mode="json"), indent=2, sort_keys=True))
    return job, path


def load_job(path: Path) -> HostLLMJob:
    try:
        return HostLLMJob.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise HostHandoffError("HOST_LLM_JOB_INVALID") from error


def accept_result(job: HostLLMJob, path: Path) -> tuple[HostLLMResult, Path]:
    try:
        result = HostLLMResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise HostHandoffError("HOST_LLM_RESULT_INVALID") from error
    if result.job_id != job.job_id or result.run_id != job.run_id:
        raise HostHandoffError("HOST_LLM_RESULT_STALE")
    if job.market_snapshot_id is None or result.research_snapshot_id != job.market_snapshot_id:
        raise HostHandoffError("HOST_LLM_RESULT_STALE")
    if job.as_of is None or result.research_as_of != job.as_of:
        raise HostHandoffError("HOST_LLM_RESULT_STALE")
    output = path.parent / f"{job.stage.value.lower()}.accepted.json"
    if output.exists():
        try:
            accepted = HostLLMResult.model_validate_json(output.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise HostHandoffError("HOST_LLM_ACCEPTED_RESULT_INVALID") from error
        if accepted != result:
            raise HostHandoffError("HOST_LLM_RESULT_DUPLICATE_CONFLICT")
        return accepted, output
    atomic_write(output, json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return result, output

def validate_symbol_research(
    result: HostLLMResult, evidence_by_symbol: Mapping[str, set[str]]
) -> dict[str, HostSymbolResearch]:
    """Validate exact symbol coverage and prevent cross-symbol evidence use."""
    analyses = {item.ticker: item for item in result.symbol_research}
    if set(analyses) != set(evidence_by_symbol) or len(analyses) != len(result.symbol_research):
        raise HostHandoffError("HOST_LLM_SYMBOL_COVERAGE_INVALID")
    declared = set(result.evidence)
    for ticker, analysis in analyses.items():
        refs = set(analysis.evidence_refs)
        if not refs or not refs <= evidence_by_symbol[ticker] or not refs <= declared:
            raise HostHandoffError("HOST_LLM_SYMBOL_EVIDENCE_INVALID")
    return analyses

def machine_handoff(*, run_id: str, job_path: Path, next_action: str) -> dict[str, str]:
    return {"RUN_ID": run_id, "JOB_PATH": str(job_path), "NEXT_ACTION": next_action}
