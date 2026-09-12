"""Bounded, evidence-first GPT-native research orchestration.

This module deliberately stops at a research decision.  It has no imports from
allocation, order construction, broker adapters, or execution quote code.  A
model may describe an investment view, but it can neither set a portfolio
weight nor create an order.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from meridian.config import ResearchSettings
from meridian.daily_research import DailyResearchInput
from meridian.runtime import RuntimePaths
from meridian.schemas import StableModel


class ResearchState(StrEnum):
    READY = "RESEARCH_READY"
    DEGRADED = "RESEARCH_DEGRADED"
    OFFLINE = "RESEARCH_OFFLINE"
    BLOCKED_DATA = "RESEARCH_BLOCKED_DATA"


class DecisionState(StrEnum):
    ACTIONABLE = "ACTIONABLE"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    NO_ACTION = "NO_ACTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class ExecutionState(StrEnum):
    READY = "EXECUTION_READY"
    BLOCKED_MARKET_CLOSED = "BLOCKED_MARKET_CLOSED"
    BLOCKED_STALE_EXECUTION_QUOTE = "BLOCKED_STALE_EXECUTION_QUOTE"
    BLOCKED_DATA_QUALITY = "BLOCKED_DATA_QUALITY"
    BLOCKED_RISK = "BLOCKED_RISK"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    PAPER_ONLY = "PAPER_ONLY"


class EvidenceCategory(StrEnum):
    PRICE = "PRICE"
    TECHNICAL = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    MACRO = "MACRO"
    NEWS = "NEWS"
    EARNINGS = "EARNINGS"
    VALUATION = "VALUATION"
    QUALITY = "QUALITY"
    MOMENTUM = "MOMENTUM"
    RISK = "RISK"
    EVENT = "EVENT"


class EvidenceSourceType(StrEnum):
    STRUCTURED_MARKET = "STRUCTURED_MARKET"
    DETERMINISTIC_MODEL = "DETERMINISTIC_MODEL"
    TRUSTED_WEB = "TRUSTED_WEB"
    GPT_DERIVED = "GPT_DERIVED"
    CACHED_RESEARCH = "CACHED_RESEARCH"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    UNVERIFIED = "UNVERIFIED"


class ClaimStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"
    CONFLICTED = "CONFLICTED"
    UNSUPPORTED = "UNSUPPORTED"


class InvocationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    PROCESS_ERROR = "PROCESS_ERROR"
    NOT_RUN = "NOT_RUN"


class ResearchEvidence(StableModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    symbol: str = Field(pattern=r"^(MERIDIAN|[A-Z][A-Z0-9.\-]{0,14})$")
    category: EvidenceCategory
    source_type: EvidenceSourceType
    source: str = Field(min_length=1, max_length=160)
    observed_at: AwareDatetime
    market_timestamp: AwareDatetime | None = None
    content: str | None = Field(default=None, max_length=4000)
    structured_value: dict[str, Any] | None = None
    confidence: float = Field(ge=0, le=1)
    freshness: str = Field(min_length=1, max_length=80)
    verification_status: VerificationStatus
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()


class ResearchClaim(StableModel):
    claim_id: str = Field(min_length=1, max_length=160)
    statement: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    status: ClaimStatus


class ModelInvocationResult(StableModel):
    status: InvocationStatus
    model: str = "NOT_AVAILABLE"
    duration_ms: int = Field(default=0, ge=0)
    output: dict[str, Any] | None = None
    schema_valid: bool = False
    error_type: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class ResearchModelRuntime(Protocol):
    def invoke(
        self,
        role: str,
        input_data: dict[str, Any],
        schema: dict[str, Any],
        budget_seconds: int,
        *,
        model: str,
        reasoning_effort: str,
    ) -> ModelInvocationResult: ...


class PrimaryAnalystOutput(StableModel):
    thesis: str = Field(min_length=1, max_length=4000)
    direction: str = Field(pattern=r"^(BULLISH|NEUTRAL|BEARISH|MIXED)$")
    key_drivers: tuple[str, ...] = ()
    supporting_claims: tuple[ResearchClaim, ...] = ()
    risks: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    time_horizon: str = Field(min_length=1, max_length=120)
    evidence_used: tuple[str, ...] = ()


class SkepticOutput(StableModel):
    challenges: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    confidence_reduction: float = Field(ge=0, le=1)
    fatal_flaw: bool = False


class Scenario(StableModel):
    description: str = Field(min_length=1, max_length=2000)
    probability: float = Field(ge=0, le=1)
    key_assumptions: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    invalidators: tuple[str, ...] = ()
    expected_direction: str = Field(pattern=r"^(BULLISH|NEUTRAL|BEARISH|MIXED)$")
    risk_factors: tuple[str, ...] = ()


class ScenarioOutput(StableModel):
    bull: Scenario
    base: Scenario
    bear: Scenario
    probability_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def probabilities_are_coherent(self) -> ScenarioOutput:
        total = self.bull.probability + self.base.probability + self.bear.probability
        if not 0.97 <= total <= 1.03:
            raise ValueError("SCENARIO_PROBABILITIES_INVALID")
        return self


class DecisionSynthesisOutput(StableModel):
    decision_state: DecisionState
    direction: str = Field(pattern=r"^(BULLISH|NEUTRAL|BEARISH|MIXED)$")
    confidence: float = Field(ge=0, le=1)
    conviction: str = Field(min_length=1, max_length=80)
    time_horizon: str = Field(min_length=1, max_length=120)
    primary_thesis: str = Field(min_length=1, max_length=4000)
    bull_probability: float = Field(ge=0, le=1)
    base_probability: float = Field(ge=0, le=1)
    bear_probability: float = Field(ge=0, le=1)
    key_support: tuple[str, ...] = ()
    key_risks: tuple[str, ...] = ()
    invalidators: tuple[str, ...] = ()
    what_changed: tuple[str, ...] = ()
    required_followup: tuple[str, ...] = ()

    @model_validator(mode="after")
    def probabilities_are_coherent(self) -> DecisionSynthesisOutput:
        total = self.bull_probability + self.base_probability + self.bear_probability
        if not 0.97 <= total <= 1.03:
            raise ValueError("SYNTHESIS_PROBABILITIES_INVALID")
        return self


class ConfidenceComposition(StableModel):
    system_confidence: float = Field(ge=0, le=1)
    llm_self_confidence: float | None = Field(default=None, ge=0, le=1)
    components: dict[str, float]


class ResearchMemoryRecord(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    last_updated: AwareDatetime
    current_thesis: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    direction: str = Field(pattern=r"^(BULLISH|NEUTRAL|BEARISH|MIXED)$")
    key_drivers: tuple[str, ...] = ()
    key_risks: tuple[str, ...] = ()
    invalidators: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    last_decision_state: DecisionState
    evidence_summary: tuple[str, ...] = ()
    recent_changes: tuple[str, ...] = ()


class ThesisChange(StrEnum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    STRENGTHENED = "STRENGTHENED"
    WEAKENED = "WEAKENED"
    REVERSED = "REVERSED"
    INVALIDATED = "INVALIDATED"


class NativeResearchResult(StableModel):
    run_id: str
    research_state: ResearchState
    decision_state: DecisionState
    execution_state: ExecutionState
    research_data_status: str
    execution_data_status: str
    evidence: tuple[ResearchEvidence, ...]
    claims: tuple[ResearchClaim, ...]
    stages: dict[str, ModelInvocationResult]
    primary: PrimaryAnalystOutput | None = None
    skeptic: SkepticOutput | None = None
    scenarios: ScenarioOutput | None = None
    synthesis: DecisionSynthesisOutput | None = None
    confidence: ConfidenceComposition
    prior_memory: ResearchMemoryRecord | None = None
    thesis_change: ThesisChange
    missing_stages: tuple[str, ...] = ()
    disagreement_score: float = Field(ge=0, le=1)
    degradation_reasons: tuple[str, ...] = ()
    authority: str = "ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"


class ResearchMemory:
    """Small, inspectable JSON memory; it is context, never market truth."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def load(self, symbol: str) -> ResearchMemoryRecord | None:
        path = self.directory / f"{symbol}.json"
        try:
            return ResearchMemoryRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return None

    def save(self, record: ResearchMemoryRecord) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{record.symbol}.json"
        temporary = self.directory / f".{record.symbol}.{uuid4().hex}.tmp"
        temporary.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
        return target


def classify_thesis_change(
    previous: ResearchMemoryRecord | None,
    *,
    direction: str,
    confidence: float,
    invalidated: bool = False,
) -> ThesisChange:
    if previous is None:
        return ThesisChange.NEW
    if invalidated:
        return ThesisChange.INVALIDATED
    if direction != previous.direction and {direction, previous.direction} != {"NEUTRAL", "MIXED"}:
        return ThesisChange.REVERSED
    delta = confidence - previous.confidence
    if delta >= 0.08:
        return ThesisChange.STRENGTHENED
    if delta <= -0.08:
        return ThesisChange.WEAKENED
    return ThesisChange.UNCHANGED


class ConfidenceComposer:
    """Deterministic confidence composition; model self-reports stay separate."""

    def compose(
        self,
        evidence: Sequence[ResearchEvidence],
        *,
        research_data_status: str,
        primary: PrimaryAnalystOutput | None,
        skeptic: SkepticOutput | None,
        scenarios: ScenarioOutput | None,
    ) -> ConfidenceComposition:
        verified = [item for item in evidence if item.verification_status is VerificationStatus.VERIFIED]
        data_quality = 1.0 if research_data_status == "PASS" else 0.0
        coverage = min(1.0, len(verified) / 4.0)
        diversity = min(1.0, len({item.source_type for item in verified}) / 3.0)
        gpt_consistency = 1.0 - (skeptic.confidence_reduction if skeptic else 0.35)
        severity = 0.0 if skeptic is None else skeptic.confidence_reduction
        skeptic_quality = 1.0 - severity
        dispersion = 0.5
        if scenarios is not None:
            probabilities = [scenarios.bull.probability, scenarios.base.probability, scenarios.bear.probability]
            dispersion = min(1.0, math.sqrt(sum((value - 1 / 3) ** 2 for value in probabilities) / 3) * 2)
        scenario_coherence = 1.0 - (dispersion * 0.35)
        value = (
            data_quality * 0.25
            + coverage * 0.20
            + diversity * 0.10
            + gpt_consistency * 0.15
            + skeptic_quality * 0.15
            + scenario_coherence * 0.15
        )
        return ConfidenceComposition(
            system_confidence=round(max(0.0, min(1.0, value)), 4),
            llm_self_confidence=primary.confidence if primary else None,
            components={
                "data_quality": round(data_quality, 4),
                "evidence_coverage": round(coverage, 4),
                "source_diversity": round(diversity, 4),
                "gpt_consistency": round(gpt_consistency, 4),
                "skeptic_severity": round(severity, 4),
                "scenario_dispersion": round(dispersion, 4),
                "historical_completeness": 1.0 if evidence else 0.0,
                "freshness": data_quality,
            },
        )


class CodexResearchModelRuntime:
    """A bounded Codex CLI implementation of the neutral runtime protocol."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        environment: Mapping[str, str] | None = None,
        runner: Callable[[Sequence[str], str, Mapping[str, str], Path, int], Any] | None = None,
    ) -> None:
        self.executable = executable
        self.environment = dict(os.environ if environment is None else environment)
        self.runner = runner

    def invoke(self, role: str, input_data: dict[str, Any], schema: dict[str, Any], budget_seconds: int, *, model: str, reasoning_effort: str) -> ModelInvocationResult:
        started = time.monotonic()
        executable = self.executable or shutil.which("codex.exe") or shutil.which("codex")
        if executable is None and self.runner is None:
            return ModelInvocationResult(status=InvocationStatus.NOT_AVAILABLE, error_type="CODEX_NOT_INSTALLED")
        environment = {key: value for key, value in self.environment.items() if key not in {"OPENAI_API_KEY", "CODEX_API_KEY", "DEEPSEEK_API_KEY"}}
        environment["PYTHONUTF8"] = "1"
        try:
            with tempfile.TemporaryDirectory(prefix="meridian-native-") as name:
                directory = Path(name)
                schema_path = directory / "schema.json"
                output_path = directory / "output.json"
                schema_path.write_text(json.dumps(schema), encoding="utf-8")
                prompt = json.dumps({"role": role, "input": input_data, "instructions": "Return only a schema-valid JSON object. Use only supplied evidence ids. This is advisory research: never generate an order, share quantity, target weight, executable price, or execution instruction."}, separators=(",", ":"), default=str)
                command = [executable or "codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only", "--skip-git-repo-check", "--output-schema", str(schema_path), "--output-last-message", str(output_path), "--color", "never", "--config", f'model_reasoning_effort="{reasoning_effort}"']
                if model.lower() not in {"", "default", "codex-default", "cli-default"}:
                    command.extend(("--model", model))
                command.append(prompt)
                if self.runner is None:
                    process = subprocess.run(command, input=json.dumps(input_data, default=str), text=True, capture_output=True, encoding="utf-8", errors="replace", cwd=directory, env=environment, timeout=budget_seconds, check=False)  # noqa: S603
                    returncode, stderr = process.returncode, process.stderr
                else:
                    process = self.runner(command, json.dumps(input_data, default=str), environment, directory, budget_seconds)
                    returncode, stderr = int(getattr(process, "returncode", 1)), str(getattr(process, "stderr", ""))
                elapsed = int((time.monotonic() - started) * 1000)
                if returncode != 0:
                    lowered = stderr.lower()
                    status = InvocationStatus.RATE_LIMITED if "rate limit" in lowered or "429" in lowered else InvocationStatus.AUTH_ERROR if "sign in" in lowered or "auth" in lowered else InvocationStatus.PROCESS_ERROR
                    return ModelInvocationResult(status=status, model=model, duration_ms=elapsed, error_type=status.value)
                output = json.loads(output_path.read_text(encoding="utf-8"))
                return ModelInvocationResult(status=InvocationStatus.SUCCESS, model=model, duration_ms=elapsed, output=output, schema_valid=True)
        except subprocess.TimeoutExpired:
            return ModelInvocationResult(status=InvocationStatus.TIMEOUT, model=model, duration_ms=int((time.monotonic() - started) * 1000), error_type="TIMEOUT")
        except TimeoutError:
            return ModelInvocationResult(status=InvocationStatus.TIMEOUT, model=model, duration_ms=int((time.monotonic() - started) * 1000), error_type="TIMEOUT")
        except (OSError, ValueError, json.JSONDecodeError):
            return ModelInvocationResult(status=InvocationStatus.SCHEMA_ERROR, model=model, duration_ms=int((time.monotonic() - started) * 1000), error_type="SCHEMA_ERROR")


class FakeResearchModelRuntime:
    """Deterministic role-to-result runtime for unit and evaluation tests."""

    def __init__(self, results: Mapping[str, ModelInvocationResult | dict[str, Any]]) -> None:
        self.results = dict(results)
        self.calls: list[tuple[str, int]] = []

    def invoke(self, role: str, input_data: dict[str, Any], schema: dict[str, Any], budget_seconds: int, *, model: str, reasoning_effort: str) -> ModelInvocationResult:
        self.calls.append((role, budget_seconds))
        candidate = self.results.get(role, ModelInvocationResult(status=InvocationStatus.NOT_AVAILABLE, model=model, error_type="NOT_CONFIGURED"))
        if isinstance(candidate, ModelInvocationResult):
            return candidate.model_copy(update={"model": candidate.model or model})
        return ModelInvocationResult(status=InvocationStatus.SUCCESS, model=model, output=candidate, schema_valid=True)


class GPTNativeResearchOrchestrator:
    """Collect facts first, then run a finite primary/skeptic/scenario/synthesis chain."""

    stage_names = ("PRIMARY_ANALYST", "SKEPTIC", "SCENARIO_ANALYSIS", "DECISION_SYNTHESIS")

    def __init__(self, runtime: ResearchModelRuntime | None = None, *, clock: Callable[[], datetime] | None = None, memory: ResearchMemory | None = None) -> None:
        self.runtime = runtime or CodexResearchModelRuntime()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.memory = memory
        self.composer = ConfidenceComposer()

    def _evidence(self, request: DailyResearchInput) -> tuple[ResearchEvidence, ...]:
        items: list[ResearchEvidence] = []
        for observation in request.observations:
            items.extend((
                ResearchEvidence(evidence_id=observation.reference, symbol=observation.ticker, category=EvidenceCategory.PRICE, source_type=EvidenceSourceType.STRUCTURED_MARKET, source="CANONICAL_MARKET_SNAPSHOT", observed_at=observation.observed_at, market_timestamp=observation.observed_at, structured_value={"last": str(observation.price)}, confidence=1.0, freshness="RESEARCH_FRESH", verification_status=VerificationStatus.VERIFIED),
                ResearchEvidence(evidence_id="det-" + observation.reference[:48], symbol=observation.ticker, category=EvidenceCategory.MOMENTUM, source_type=EvidenceSourceType.DETERMINISTIC_MODEL, source="DAILY_RETURN_ANALYTICS", observed_at=request.analysis_cutoff, market_timestamp=observation.observed_at, structured_value={"daily_return": str(observation.daily_return)}, confidence=1.0, freshness="RESEARCH_FRESH", verification_status=VerificationStatus.VERIFIED),
            ))
        package = request.evidence_package or {}
        raw = package.get("evidence", []) if isinstance(package, dict) else []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not item.get("evidence_id"):
                continue
            try:
                timestamp = datetime.fromisoformat(str(item.get("timestamp") or request.analysis_cutoff.isoformat()))
                if timestamp.tzinfo is None:
                    continue
                items.append(ResearchEvidence(evidence_id="packet-" + str(item["evidence_id"]), symbol=str(item.get("symbol") or "MERIDIAN"), category=EvidenceCategory.FUNDAMENTAL, source_type=EvidenceSourceType.TRUSTED_WEB, source=str(item.get("source") or "RETRIEVAL_PACKET"), observed_at=timestamp, market_timestamp=timestamp, content=str(item.get("field") or "structured retrieval"), confidence=float(item.get("confidence", 0.5)), freshness="RESEARCH_PACKET", verification_status=VerificationStatus.VERIFIED if item.get("validation_status") == "PASS" else VerificationStatus.DEGRADED))
            except (TypeError, ValueError):
                continue
        return tuple(items)

    @staticmethod
    def _parse(result: ModelInvocationResult, model_type: type[StableModel], allowed_ids: set[str]) -> tuple[ModelInvocationResult, StableModel | None]:
        if result.status is not InvocationStatus.SUCCESS or result.output is None:
            return result, None
        try:
            parsed = model_type.model_validate(result.output)
            references: set[str] = set()
            if isinstance(parsed, PrimaryAnalystOutput):
                references.update(parsed.evidence_used)
                for claim in parsed.supporting_claims:
                    references.update(claim.supporting_evidence_ids)
                    references.update(claim.contradicting_evidence_ids)
            elif isinstance(parsed, SkepticOutput):
                references.update(parsed.contradicting_evidence)
            if not references <= allowed_ids:
                raise ValueError("UNSUPPORTED_EVIDENCE_ID")
            return result.model_copy(update={"schema_valid": True}), parsed
        except ValueError:
            return ModelInvocationResult(status=InvocationStatus.SCHEMA_ERROR, model=result.model, duration_ms=result.duration_ms, schema_valid=False, error_type="SCHEMA_ERROR"), None

    def run(self, request: DailyResearchInput, *, research_data_status: str, execution_data_status: str, execution_state: ExecutionState, settings: ResearchSettings, run_id: str | None = None) -> NativeResearchResult:
        started = time.monotonic()
        run_id = run_id or "native-" + uuid4().hex
        evidence = self._evidence(request)
        stages = {name: ModelInvocationResult(status=InvocationStatus.NOT_RUN) for name in self.stage_names}
        memories = [self.memory.load(item.ticker) for item in request.observations] if self.memory else []
        prior = next((item for item in memories if item is not None), None)
        if research_data_status != "PASS" or not evidence:
            confidence = self.composer.compose(evidence, research_data_status=research_data_status, primary=None, skeptic=None, scenarios=None)
            return NativeResearchResult(run_id=run_id, research_state=ResearchState.BLOCKED_DATA, decision_state=DecisionState.INSUFFICIENT_EVIDENCE, execution_state=execution_state, research_data_status=research_data_status, execution_data_status=execution_data_status, evidence=evidence, claims=(), stages=stages, confidence=confidence, prior_memory=prior, thesis_change=ThesisChange.UNCHANGED, missing_stages=self.stage_names, disagreement_score=0.0, degradation_reasons=("FOUNDATIONAL_STRUCTURED_DATA_INVALID",))
        allowed_ids = {item.evidence_id for item in evidence}
        base_input = {"research_question": "Assess the supplied symbols using only normalized evidence.", "analysis_cutoff": request.analysis_cutoff.isoformat(), "evidence": [item.model_dump(mode="json") for item in evidence], "prior_thesis": prior.model_dump(mode="json") if prior else None, "data_limitations": ["Prior research is context only and cannot override current evidence.", "No execution authority."]}
        budget = settings.native_budget
        def remaining() -> int:
            return max(0, int(budget.total_seconds - (time.monotonic() - started)))
        primary: PrimaryAnalystOutput | None = None
        skeptic: SkepticOutput | None = None
        scenarios: ScenarioOutput | None = None
        synthesis: DecisionSynthesisOutput | None = None
        if settings.live_enabled and remaining() > 0:
            raw = self.runtime.invoke("PRIMARY_ANALYST", base_input, PrimaryAnalystOutput.model_json_schema(), min(budget.primary_seconds, remaining()), model=settings.primary_model or settings.model, reasoning_effort=settings.reasoning_effort)
            stages["PRIMARY_ANALYST"], parsed = self._parse(raw, PrimaryAnalystOutput, allowed_ids)
            primary = parsed if isinstance(parsed, PrimaryAnalystOutput) else None
            skeptic_input = {**base_input, "primary": primary.model_dump(mode="json") if primary else None, "instruction": "Attempt to disprove the primary thesis. Do not optimize for a trade."}
            if remaining() > 0:
                raw = self.runtime.invoke("SKEPTIC", skeptic_input, SkepticOutput.model_json_schema(), min(budget.skeptic_seconds, remaining()), model=settings.skeptic_model or settings.model, reasoning_effort=settings.reasoning_effort)
                stages["SKEPTIC"], parsed = self._parse(raw, SkepticOutput, allowed_ids)
                skeptic = parsed if isinstance(parsed, SkepticOutput) else None
            if remaining() > 0:
                raw = self.runtime.invoke("SCENARIO_ANALYSIS", {**base_input, "primary": primary.model_dump(mode="json") if primary else None, "skeptic": skeptic.model_dump(mode="json") if skeptic else None}, ScenarioOutput.model_json_schema(), min(budget.scenario_seconds, remaining()), model=settings.scenario_model or settings.model, reasoning_effort=settings.reasoning_effort)
                stages["SCENARIO_ANALYSIS"], parsed = self._parse(raw, ScenarioOutput, allowed_ids)
                scenarios = parsed if isinstance(parsed, ScenarioOutput) else None
            if primary is not None and remaining() > 0:
                raw = self.runtime.invoke("DECISION_SYNTHESIS", {**base_input, "primary": primary.model_dump(mode="json"), "skeptic": skeptic.model_dump(mode="json") if skeptic else None, "scenarios": scenarios.model_dump(mode="json") if scenarios else None, "risk_constraints": {"execution_authority": "NONE"}}, DecisionSynthesisOutput.model_json_schema(), min(budget.synthesis_seconds, remaining()), model=settings.synthesis_model or settings.model, reasoning_effort=settings.reasoning_effort)
                stages["DECISION_SYNTHESIS"], parsed = self._parse(raw, DecisionSynthesisOutput, allowed_ids)
                synthesis = parsed if isinstance(parsed, DecisionSynthesisOutput) else None
        else:
            stages = {name: ModelInvocationResult(status=InvocationStatus.NOT_AVAILABLE, model="DISABLED", error_type="LIVE_RESEARCH_DISABLED") for name in self.stage_names}
        missing = tuple(name for name, result in stages.items() if result.status is not InvocationStatus.SUCCESS)
        disagreement = min(1.0, (skeptic.confidence_reduction if skeptic else 0.0) + (0.4 if skeptic and skeptic.fatal_flaw else 0.0))
        confidence = self.composer.compose(evidence, research_data_status=research_data_status, primary=primary, skeptic=skeptic, scenarios=scenarios)
        claims = primary.supporting_claims if primary else ()
        if not any(result.status is InvocationStatus.SUCCESS for result in stages.values()):
            transient_failure = any(
                result.status in {
                    InvocationStatus.TIMEOUT,
                    InvocationStatus.RATE_LIMITED,
                    InvocationStatus.AUTH_ERROR,
                    InvocationStatus.SCHEMA_ERROR,
                    InvocationStatus.PROCESS_ERROR,
                }
                for result in stages.values()
            )
            state, decision = (
                (ResearchState.DEGRADED, DecisionState.RESEARCH_ONLY)
                if transient_failure
                else (ResearchState.OFFLINE, DecisionState.RESEARCH_ONLY)
            )
        elif missing:
            state, decision = ResearchState.DEGRADED, DecisionState.RESEARCH_ONLY
        else:
            state, decision = ResearchState.READY, synthesis.decision_state if synthesis else DecisionState.RESEARCH_ONLY
        if skeptic and (skeptic.fatal_flaw or disagreement >= 0.65):
            decision = DecisionState.CONFLICTING_EVIDENCE
        direction = synthesis.direction if synthesis else primary.direction if primary else "NEUTRAL"
        change = classify_thesis_change(prior, direction=direction, confidence=confidence.system_confidence, invalidated=bool(skeptic and skeptic.fatal_flaw))
        result = NativeResearchResult(run_id=run_id, research_state=state, decision_state=decision, execution_state=execution_state, research_data_status=research_data_status, execution_data_status=execution_data_status, evidence=evidence, claims=claims, stages=stages, primary=primary, skeptic=skeptic, scenarios=scenarios, synthesis=synthesis, confidence=confidence, prior_memory=prior, thesis_change=change, missing_stages=missing, disagreement_score=round(disagreement, 4), degradation_reasons=tuple(sorted({stage.error_type or stage.status.value for stage in stages.values() if stage.status is not InvocationStatus.SUCCESS})))
        self._save_memory(result, request)
        return result

    def _save_memory(self, result: NativeResearchResult, request: DailyResearchInput) -> None:
        if self.memory is None or result.research_state is ResearchState.BLOCKED_DATA:
            return
        direction = result.synthesis.direction if result.synthesis else result.primary.direction if result.primary else "NEUTRAL"
        thesis = result.synthesis.primary_thesis if result.synthesis else result.primary.thesis if result.primary else "Deterministic evidence available; GPT reasoning unavailable."
        drivers = result.primary.key_drivers if result.primary else ()
        risks = result.synthesis.key_risks if result.synthesis else result.primary.risks if result.primary else ()
        invalidators = result.synthesis.invalidators if result.synthesis else ()
        for symbol in {item.symbol for item in result.evidence if item.symbol != "MERIDIAN"}:
            self.memory.save(ResearchMemoryRecord(symbol=symbol, last_updated=self.clock(), current_thesis=thesis, confidence=result.confidence.system_confidence, direction=direction, key_drivers=drivers, key_risks=risks, invalidators=invalidators, open_questions=result.primary.unknowns if result.primary else (), last_decision_state=result.decision_state, evidence_summary=tuple(item.evidence_id for item in result.evidence if item.symbol == symbol)[:12], recent_changes=(result.thesis_change.value,)))


def persist_research_trace(result: NativeResearchResult, paths: RuntimePaths, analysis_time: datetime) -> Path:
    """Persist bounded audit metadata, intentionally excluding raw prompts and account context."""
    directory = paths.reports / analysis_time.date().isoformat() / result.run_id
    directory.mkdir(parents=True, exist_ok=True)
    trace = {"schema_version": "meridian-research-trace.v1", "run_id": result.run_id, "research_state": result.research_state.value, "decision_state": result.decision_state.value, "execution_state": result.execution_state.value, "evidence_count": len(result.evidence), "stages": [{"stage": name, "input_evidence_ids": [item.evidence_id for item in result.evidence], "output_claim_ids": [claim.claim_id for claim in result.claims] if name == "PRIMARY_ANALYST" else [], "duration_ms": stage.duration_ms, "status": stage.status.value, "schema_valid": stage.schema_valid, "error_type": stage.error_type} for name, stage in result.stages.items()], "degradation_reasons": list(result.degradation_reasons), "authority": result.authority}
    path = directory / "research_trace.json"
    temporary = directory / f"research_trace.{uuid4().hex}.tmp"
    temporary.write_text(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path
