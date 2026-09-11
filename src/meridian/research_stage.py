"""Bounded canonical advisory research through a provider-neutral boundary."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from meridian.codex_provider import (
    CodexCliProvider,
    CodexError,
)
from meridian.config import ResearchSettings
from meridian.daily_research import (
    DailyResearchInput,
    DailyResearchOutput,
    ResearchDecisionContext,
    ResearchProviderStatus,
    ResearchStageResult,
    validate_replay,
)
from meridian.research_agents.preparation import ResearchPreparationService

Status = ResearchProviderStatus


class ResearchProvider(Protocol):
    def run(
        self, request: DailyResearchInput, settings: ResearchSettings
    ) -> object: ...


_NEXT_ACTIONS = {
    CodexError.NOT_INSTALLED.value: (
        "Install the Codex CLI and ensure codex.exe is on PATH; execution remains blocked."
    ),
    CodexError.AUTH_REQUIRED.value: (
        "Open Codex CLI once and sign in with ChatGPT; no API key is accepted."
    ),
    CodexError.TIMEOUT.value: (
        "Review the Codex timeout and retry one later run with fresh inputs."
    ),
    CodexError.RATE_LIMITED.value: (
        "Wait for ChatGPT-managed Codex capacity to recover; do not switch providers."
    ),
    CodexError.PROCESS_ERROR.value: (
        "Inspect the local Codex CLI process and sanitized diagnostics, then retry "
        "with fresh inputs."
    ),
    CodexError.SCHEMA_ERROR.value: (
        "Inspect the schema-validity diagnostic; one repair retry was already bounded."
    ),
    CodexError.EMPTY_RESPONSE.value: (
        "Codex produced no final structured response; execution remains blocked."
    ),
    CodexError.OUTPUT_MISSING.value: (
        "Codex did not create the required output file; execution remains blocked."
    ),
    CodexError.CONFIG_INVALID.value: (
        "Correct Meridian Codex model, reasoning, timeout, prompt or schema configuration."
    ),
}


class CanonicalResearchStage:
    """Validate Meridian gates, then delegate reasoning to a local provider."""

    def __init__(
        self,
        *,
        provider: ResearchProvider | None = None,
        preparation: ResearchPreparationService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider or CodexCliProvider()
        self.preparation = preparation
        self.clock = clock or (lambda: datetime.now(UTC))
        self.provenance = (
            "FIXTURE"
            if bool(getattr(self.provider, "_injected_runner", False))
            else "CODEX_CLI"
        )

    def run(
        self,
        request: DailyResearchInput,
        settings: ResearchSettings | None,
        *,
        replay: ResearchStageResult | None = None,
    ) -> ResearchStageResult:
        started = self.clock()
        tick = time.monotonic()
        attempts = 0
        sent = received = None
        provenance = "NONE"
        structured_response: dict[str, object] | None = None
        provider_diagnostics: dict[str, object] = {}
        preparation_diagnostics: dict[str, object] = {}
        result_model = request.model

        def finish(
            status: Status,
            code: str | None = None,
            output: DailyResearchOutput | None = None,
            next_action: str | None = None,
        ) -> ResearchStageResult:
            return ResearchStageResult(
                context=ResearchDecisionContext(
                    research_run_id="research-" + uuid4().hex,
                    parent_run_id=request.parent_run_id,
                    input_hash=request.input_hash,
                    analysis_cutoff=request.analysis_cutoff,
                    status=status,
                    output=output,
                ),
                prompt_created_at=started,
                started_at=started,
                finished_at=self.clock(),
                request_sent_at=sent,
                response_received_at=received,
                duration_seconds=round(time.monotonic() - tick, 4),
                attempts=attempts,
                provider=(
                    "CODEX_CLI"
                    if provenance in {"CODEX_CLI", "FIXTURE"}
                    else request.provider
                ),
                model=result_model,
                provenance=provenance,  # type: ignore[arg-type]
                error_code=code,
                next_action=next_action
                or (
                    "Review Codex model inferences; deterministic risk and manual "
                    "gates remain authoritative."
                    if status is Status.AVAILABLE
                    else "No research action is authorized; correct the reported "
                    "condition and rerun with fresh inputs."
                ),
                structured_response=structured_response,
                provider_diagnostics=provider_diagnostics,
                preparation_diagnostics=preparation_diagnostics,
            )

        if (
            request.freshness_status != "PASS"
            or not request.observations
            or not request.provider_provenance
        ):
            return finish(Status.BLOCKED, "RESEARCH_INPUT_NOT_READY")
        if request.mode == "REPLAY":
            if replay is None:
                return finish(Status.BLOCKED, "RESEARCH_REPLAY_MISSING")
            try:
                validate_replay(
                    request,
                    replay,
                    replay_time=started,
                    max_age_seconds=(
                        settings.live_as_of_tolerance_seconds if settings else 86400
                    ),
                )
            except ValueError:
                return finish(Status.BLOCKED, "RESEARCH_REPLAY_INVALID_OR_STALE")
            provenance = "REPLAY"
            received = replay.response_received_at
            structured_response = replay.structured_response
            provider_diagnostics = replay.provider_diagnostics
            return finish(Status.AVAILABLE, output=replay.context.output)
        if settings is None or not settings.live_enabled:
            return finish(Status.NOT_RUN, "LIVE_RESEARCH_DISABLED")
        if request.provider != settings.provider or request.model != settings.model:
            return finish(Status.BLOCKED, "RESEARCH_CONFIG_MISMATCH")
        if request.provider.lower() not in {"codex", "codex_cli"}:
            return finish(Status.NOT_CONFIGURED, "RESEARCH_PROVIDER_UNSUPPORTED")
        if request.mode == "FIXTURE" and self.provenance != "FIXTURE":
            return finish(Status.BLOCKED, "FIXTURE_CANNOT_CALL_LIVE_PROVIDER")
        age = (started - request.analysis_cutoff).total_seconds()
        if age < 0 or age > settings.live_as_of_tolerance_seconds:
            return finish(Status.BLOCKED, "RESEARCH_CUTOFF_INVALID_OR_STALE")
        if len(request.observations) > settings.budget.max_graph_tickers_per_run:
            return finish(Status.BLOCKED, "RESEARCH_UNIVERSE_BUDGET_EXCEEDED")

        if self.preparation is not None:
            try:
                prepared = self.preparation.prepare(request, settings)
            except RuntimeError as error:
                code = str(error) if str(error) else "DATA_RETRIEVAL_FAILED"
                preparation_diagnostics = {
                    "status": "DATA_RETRIEVAL_FAILED",
                    "error_code": code,
                    "decision": "NO_ACTION",
                }
                return finish(
                    Status.DATA_RETRIEVAL_FAILED,
                    code,
                    next_action="Correct the strategy/retrieval configuration; execution remains blocked.",
                )
            request = prepared.request
            preparation_diagnostics = {
                "status": prepared.package.status.value,
                "initial_completeness": str(prepared.initial_completeness),
                "final_completeness": str(prepared.package.quality.completeness),
                "quality_score": prepared.package.quality.score,
                "quality_grade": prepared.package.quality.grade.value,
                "source_count": prepared.package.source_count,
                "retrieval_rounds": prepared.package.rounds,
                "planner_rounds": prepared.planner_rounds,
                "requirements": len(prepared.package.requirements),
                "retrieved": sum(
                    item.status.value in {"AVAILABLE", "RETRIEVED"}
                    for item in prepared.package.requirements
                ),
                "failed": [
                    item.key
                    for item in prepared.package.requirements
                    if item.status.value in {"MISSING", "FAILED", "CONFLICT"}
                ],
                "blocking_missing": list(prepared.package.quality.blocking_missing),
                "sources": sorted(
                    {f"{item.provider}:{item.source}" for item in prepared.package.evidence}
                ),
                "evidence_catalog": [
                    {
                        "evidence_id": item.evidence_id,
                        "requirement_key": item.requirement_key,
                        "field": item.field,
                        "symbol": item.symbol,
                        "provider": item.provider,
                        "source": item.source,
                        "timestamp": item.timestamp.isoformat(),
                        "retrieved_at": item.retrieved_at.isoformat(),
                        "confidence": str(item.confidence),
                        "validation_status": item.validation_status.value,
                    }
                    for item in prepared.package.evidence
                ],
                "provider_results": [
                    item.model_dump(mode="json") for item in prepared.package.provider_results
                ],
                "conflicts": [
                    item.model_dump(mode="json") for item in prepared.package.conflicts
                ],
            }
            if prepared.error_code is not None or prepared.package.quality.blocking_missing:
                try:
                    status = Status(prepared.error_code) if prepared.error_code else None
                except ValueError:
                    status = None
                if status is None:
                    status = (
                        Status.GPT_PLANNER_FAILED
                        if prepared.error_code == "GPT_PLANNER_FAILED"
                        else Status.SOURCE_CONFLICT
                        if prepared.package.status.value == "SOURCE_CONFLICT"
                        else Status.INSUFFICIENT_DATA
                    )
                return finish(
                    status,
                    prepared.error_code or prepared.package.status.value,
                    next_action=(
                        "Review the explicit blocking_missing list and provider results; "
                        "no missing value was inferred and execution remains blocked."
                    ),
                )

        provenance = self.provenance
        sent = self.clock()
        provider_result = self.provider.run(request, settings)
        if not (
            hasattr(provider_result, "attempts")
            and hasattr(provider_result, "diagnostics")
            and hasattr(provider_result, "response")
        ):
            return finish(
                Status.CODEX_PROCESS_ERROR,
                CodexError.PROCESS_ERROR.value,
                next_action=_NEXT_ACTIONS[CodexError.PROCESS_ERROR.value],
            )
        received = self.clock()
        attempts = int(provider_result.attempts)  # type: ignore[attr-defined]
        diagnostics = provider_result.diagnostics  # type: ignore[attr-defined]
        provider_diagnostics = diagnostics.model_dump(mode="json")
        result_model = diagnostics.model_requested
        response = provider_result.response  # type: ignore[attr-defined]
        if response is None:
            code = (
                diagnostics.error_class
                or CodexError.PROCESS_ERROR.value
            )
            try:
                status = Status(code)
            except ValueError:
                status = Status.CODEX_PROCESS_ERROR
                code = CodexError.PROCESS_ERROR.value
            return finish(status, code, next_action=_NEXT_ACTIONS.get(code))

        structured_response = response.model_dump(mode="json")
        if response.status == "NO_ACTION":
            return finish(
                Status.NO_ACTION,
                "CODEX_NO_ACTION",
                next_action=(
                    "Codex found no justified action; preserve NO_ACTION and all "
                    "existing gates."
                ),
            )
        if response.status == "INSUFFICIENT_DATA":
            return finish(
                Status.INSUFFICIENT_DATA,
                "CODEX_INSUFFICIENT_DATA",
                next_action=(
                    "Supply fresh missing evidence identified in data_gaps; do not "
                    "invent or fetch it implicitly."
                ),
            )
        output = DailyResearchOutput(results=response.results)
        output.validate_input(request)
        return finish(Status.AVAILABLE, output=output)
