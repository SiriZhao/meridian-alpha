"""Explicit Codex-host handoff artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import Field, model_validator

from meridian.runtime import RuntimePaths
from meridian.runtime_io import atomic_write
from meridian.schemas import StableModel


class HostJobStage(StrEnum):
    RESEARCH = "HOST_LLM_RESEARCH"
    ADVISORY = "HOST_LLM_ADVISORY"


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
    output = path.parent / f"{job.stage.value.lower()}.accepted.json"
    atomic_write(output, json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return result, output


def machine_handoff(*, run_id: str, job_path: Path, next_action: str) -> dict[str, str]:
    return {"RUN_ID": run_id, "JOB_PATH": str(job_path), "NEXT_ACTION": next_action}
