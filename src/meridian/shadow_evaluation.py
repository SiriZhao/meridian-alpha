"""Live GPT shadow records and deterministic quality/calibration evaluation.

Shadow mode is intentionally outside the canonical closure path.  A runner in
this module can read current evidence and invoke GPT, but it never receives a
portfolio, allocator, risk engine, order planner, or execution authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from statistics import mean, pstdev
from typing import Any
from uuid import uuid4

from pydantic import Field

from meridian.config import ModelRoutingPolicy, ResearchSettings
from meridian.daily_research import DailyResearchInput
from meridian.gpt_native_research import (
    ClaimStatus,
    CodexResearchModelRuntime,
    GPTNativeResearchOrchestrator,
    LiveModelPreflight,
    NativeResearchResult,
    ResearchClaim,
    ResearchEvidence,
    ResearchMemory,
    ScenarioOutput,
)
from meridian.runtime import RuntimePaths
from meridian.schemas import StableModel


class ShadowMode(StrEnum):
    OFFLINE = "OFFLINE"
    SHADOW_LIVE = "SHADOW_LIVE"
    PRODUCTION_RESEARCH = "PRODUCTION_RESEARCH"


class PromotionStatus(StrEnum):
    NOT_READY = "NOT_READY"
    SHADOW_ACCEPTABLE = "SHADOW_ACCEPTABLE"
    CANDIDATE_FOR_PRODUCTION_RESEARCH = "CANDIDATE_FOR_PRODUCTION_RESEARCH"


class GPTResearchPromotionAssessment(StableModel):
    status: PromotionStatus
    reasons: tuple[str, ...]
    shadow_only: bool = True
    execution_authority: str = "NONE"

class GroundingCheck(StableModel):
    claim_id: str
    valid_evidence_ids: tuple[str, ...] = ()
    invalid_evidence_ids: tuple[str, ...] = ()
    status: str = "UNKNOWN"


class QualityMetrics(StableModel):
    evidence_grounding_rate: float | None = Field(default=None, ge=0, le=1)
    unsupported_claim_rate: float | None = Field(default=None, ge=0, le=1)
    invalid_evidence_reference_rate: float | None = Field(default=None, ge=0, le=1)
    contradiction_detection_rate: float | None = Field(default=None, ge=0, le=1)
    schema_success_rate: float | None = Field(default=None, ge=0, le=1)
    stage_completion_rate: float | None = Field(default=None, ge=0, le=1)
    hallucinated_market_fact_count: int = Field(default=0, ge=0)
    unverifiable_numeric_claim_count: int = Field(default=0, ge=0)
    stale_evidence_usage_count: int = Field(default=0, ge=0)
    confidence_vs_evidence_gap: float | None = Field(default=None, ge=0, le=1)
    analyst_skeptic_disagreement: float | None = Field(default=None, ge=0, le=1)
    scenario_probability_validity: float | None = Field(default=None, ge=0, le=1)
    memory_consistency: float | None = Field(default=None, ge=0, le=1)
    latency_ms: int = Field(default=0, ge=0)
    skeptic_added_information: float | None = Field(default=None, ge=0, le=1)
    skeptic_duplicate_rate: float | None = Field(default=None, ge=0, le=1)
    skeptic_valid_challenges: int = Field(default=0, ge=0)
    skeptic_false_challenges: int = Field(default=0, ge=0)
    fatal_flaw_detected: bool = False
    scenario_overlap_score: float | None = Field(default=None, ge=0, le=1)
    hallucination_flags: tuple[str, ...] = ()
    metric_applicability: dict[str, str] = Field(default_factory=dict)


class ResearchComparison(StableModel):
    deterministic_direction: str
    deterministic_confidence: float
    shadow_direction: str
    shadow_confidence: float | None = None
    prior_direction: str | None = None
    what_gpt_added: tuple[str, ...] = ()
    what_gpt_contradicted: tuple[str, ...] = ()
    what_gpt_missed: tuple[str, ...] = ()
    what_deterministic_missed: tuple[str, ...] = ()
    what_changed_from_prior: tuple[str, ...] = ()
    disagreement: str = "UNKNOWN"


class ShadowResearchRecord(StableModel):
    schema_version: str = "meridian-shadow-research.v1"
    run_id: str
    shadow_only: bool = True
    mode: str = ShadowMode.SHADOW_LIVE
    symbols: tuple[str, ...]
    evidence_count: int = Field(default=0, ge=0)
    model_route: dict[str, dict[str, Any]]
    stages: dict[str, dict[str, Any]]
    primary: dict[str, Any] | None = None
    skeptic: dict[str, Any] | None = None
    scenario: dict[str, Any] | None = None
    synthesis: dict[str, Any] | None = None
    # ``system_confidence`` is retained as an internal ceiling/promotion input.
    # The explicit fields below prevent it being presented as GPT confidence.
    system_confidence: float | None = Field(default=None, ge=0, le=1)
    deterministic_system_confidence: float | None = Field(default=None, ge=0, le=1)
    gpt_shadow_confidence: float | None = Field(default=None, ge=0, le=1)
    combined_shadow_confidence: float | None = Field(default=None, ge=0, le=1)
    gpt_confidence_status: str = "NOT_AVAILABLE"
    llm_self_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    decision_state: str
    direction: str
    quality_metrics: QualityMetrics
    comparison: ResearchComparison
    latency_ms: int = Field(ge=0)
    usage_by_stage: dict[str, dict[str, Any]] = Field(default_factory=dict)
    orders_created: int = 0
    orders_executed: int = 0
    shadow_decision_authority: str = "NONE"
    live_preflight: LiveModelPreflight | None = None


class GroundingValidator:
    """Validate claim citations without accepting GPT text as a market fact."""

    _number = re.compile(r"(?<![A-Za-z])[+-]?(?:\d+(?:\.\d+)?%?|\.\d+%?)")

    def validate(
        self,
        claims: Sequence[ResearchClaim],
        evidence: Sequence[ResearchEvidence],
    ) -> tuple[GroundingCheck, ...]:
        allowed = {item.evidence_id for item in evidence}
        checks: list[GroundingCheck] = []
        for claim in claims:
            cited = set(claim.supporting_evidence_ids) | set(claim.contradicting_evidence_ids)
            valid = tuple(sorted(cited & allowed))
            invalid = tuple(sorted(cited - allowed))
            status = "SUPPORTED" if cited and not invalid and claim.status is not ClaimStatus.UNSUPPORTED else "UNSUPPORTED"
            checks.append(
                GroundingCheck(
                    claim_id=claim.claim_id,
                    valid_evidence_ids=valid,
                    invalid_evidence_ids=invalid,
                    status=status,
                )
            )
        return tuple(checks)

    def hallucination_flags(
        self, claims: Sequence[ResearchClaim], evidence: Sequence[ResearchEvidence]
    ) -> tuple[str, ...]:
        flags: list[str] = []
        for claim in claims:
            if self._number.search(claim.statement) and not claim.supporting_evidence_ids:
                flags.append(f"{claim.claim_id}:UNVERIFIABLE_NUMERIC_CLAIM")
        known_sources = {item.source for item in evidence}
        for claim in claims:
            lowered = claim.statement.lower()
            if any(token in lowered for token in ("according to", "reported by", "earnings")) and not claim.supporting_evidence_ids:
                flags.append(f"{claim.claim_id}:UNVERIFIED_SOURCE_OR_EVENT")
            if known_sources and any(source.lower() in lowered for source in known_sources):
                continue
        return tuple(sorted(set(flags)))


class ResearchQualityEvaluator:
    """Deterministic quality metrics; missing ground truth remains ``None``."""

    def __init__(self, grounding: GroundingValidator | None = None) -> None:
        self.grounding = grounding or GroundingValidator()

    @staticmethod
    def _scenario_quality(scenarios: ScenarioOutput | None) -> tuple[float | None, float | None]:
        if scenarios is None:
            return None, None
        values = [scenarios.bull.probability, scenarios.base.probability, scenarios.bear.probability]
        total = sum(values)
        validity = 1.0 if 0.97 <= total <= 1.03 else 0.0
        descriptions = [
            scenarios.bull.description.strip().lower(),
            scenarios.base.description.strip().lower(),
            scenarios.bear.description.strip().lower(),
        ]
        overlap = 1.0 - len(set(descriptions)) / 3.0
        return validity, max(0.0, min(1.0, overlap))

    def evaluate(self, result: NativeResearchResult) -> QualityMetrics:
        checks = self.grounding.validate(result.claims, result.evidence)
        flags = self.grounding.hallucination_flags(result.claims, result.evidence)
        claims_count = len(result.claims)
        grounding_rate = (
            sum(item.status == "SUPPORTED" for item in checks) / len(checks) if checks else None
        )
        invalid_rate = (
            sum(bool(item.invalid_evidence_ids) for item in checks) / len(checks) if checks else None
        )
        unsupported_rate = (
            sum(item.status is ClaimStatus.UNSUPPORTED for item in result.claims) / claims_count
            if claims_count
            else None
        )
        stage_count = len(result.stages)
        completed = sum(stage.status.value == "SUCCESS" for stage in result.stages.values())
        contradiction_rate = None
        skeptic_added = None
        duplicate_rate = None
        valid_challenges = false_challenges = 0
        if result.skeptic is not None:
            cited = set(result.skeptic.contradicting_evidence)
            valid_challenges = len(cited & {item.evidence_id for item in result.evidence})
            false_challenges = len(cited - {item.evidence_id for item in result.evidence})
            contradiction_rate = valid_challenges / max(1, len(cited))
            challenge_text = {item.strip().lower() for item in result.skeptic.challenges}
            primary_text = {item.strip().lower() for item in (result.primary.key_drivers if result.primary else ())}
            duplicate_rate = len(challenge_text & primary_text) / max(1, len(challenge_text))
            skeptic_added = 1.0 - duplicate_rate
        scenario_validity, overlap = self._scenario_quality(result.scenarios)
        stale = sum(item.freshness not in {"RESEARCH_FRESH", "RESEARCH_PACKET"} for item in result.evidence)
        gap = None
        if result.primary is not None:
            gap = abs(result.primary.confidence - result.confidence.system_confidence)
        memory_consistency = None
        if result.prior_memory is not None and result.primary is not None:
            memory_consistency = 1.0 if result.prior_memory.direction == result.primary.direction else 0.0
        measured_invocations: dict[str, int] = {}
        for name, item in result.stages.items():
            key = str(item.diagnostic.get("shared_invocation_id") or "RESEARCH_CHAIN") if item.diagnostic.get("shared_invocation") else name
            measured_invocations[key] = max(measured_invocations.get(key, 0), item.duration_ms)
        latency = sum(measured_invocations.values())
        applicability = {
            "grounding_rate": "APPLICABLE" if claims_count else "NOT_APPLICABLE_NO_MODEL_OUTPUT",
            "hallucination_rate": "APPLICABLE" if claims_count else "NOT_APPLICABLE_NO_MODEL_OUTPUT",
            "unsupported_claim_rate": "APPLICABLE" if claims_count else "NOT_APPLICABLE_NO_MODEL_OUTPUT",
            "scenario_probability_validity": "APPLICABLE" if result.scenarios else "NOT_APPLICABLE_NO_MODEL_OUTPUT",
            "skeptic_value": "APPLICABLE" if result.skeptic else "NOT_APPLICABLE_NO_MODEL_OUTPUT",
        }
        return QualityMetrics(
            evidence_grounding_rate=grounding_rate,
            unsupported_claim_rate=unsupported_rate,
            invalid_evidence_reference_rate=invalid_rate,
            contradiction_detection_rate=contradiction_rate,
            schema_success_rate=completed / stage_count if stage_count else None,
            stage_completion_rate=completed / stage_count if stage_count else None,
            hallucinated_market_fact_count=len(flags) + int(result.stages["PRIMARY_ANALYST"].diagnostic.get("rejected_numeric_claim_count") or 0),
            unverifiable_numeric_claim_count=sum("UNVERIFIABLE_NUMERIC_CLAIM" in flag for flag in flags),
            stale_evidence_usage_count=stale,
            confidence_vs_evidence_gap=gap,
            analyst_skeptic_disagreement=result.disagreement_score if result.skeptic is not None else None,
            scenario_probability_validity=scenario_validity,
            memory_consistency=memory_consistency,
            latency_ms=latency,
            skeptic_added_information=skeptic_added,
            skeptic_duplicate_rate=duplicate_rate,
            skeptic_valid_challenges=valid_challenges,
            skeptic_false_challenges=false_challenges,
            fatal_flaw_detected=bool(result.skeptic and result.skeptic.fatal_flaw),
            scenario_overlap_score=overlap,
            hallucination_flags=flags,
            metric_applicability=applicability,
        )


def _deterministic_baseline(request: DailyResearchInput) -> tuple[str, float, tuple[str, ...]]:
    if not request.observations:
        return "NEUTRAL", 0.0, ()
    positive = sum(item.daily_return is not None and item.daily_return > 0 for item in request.observations)
    negative = sum(item.daily_return is not None and item.daily_return < 0 for item in request.observations)
    direction = "BULLISH" if positive > negative else "BEARISH" if negative > positive else "NEUTRAL"
    confidence = abs(positive - negative) / len(request.observations)
    support = tuple(item.reference for item in request.observations if item.daily_return is not None and (item.daily_return > 0) == (direction == "BULLISH"))
    return direction, confidence, support


class ShadowResearchRunner:
    """Run GPT in shadow mode and persist only bounded, non-authoritative output."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        orchestrator: GPTNativeResearchOrchestrator | None = None,
        evaluator: ResearchQualityEvaluator | None = None,
    ) -> None:
        self.paths = paths
        self.orchestrator = orchestrator or GPTNativeResearchOrchestrator(
            memory=ResearchMemory(paths.data / "research" / "memory")
        )
        self.evaluator = evaluator or ResearchQualityEvaluator()

    @staticmethod
    def route(settings: ResearchSettings) -> dict[str, dict[str, Any]]:
        defaults = {
            "PRIMARY_ANALYST": (settings.primary_model or settings.model, settings.native_budget.primary_seconds),
            "SKEPTIC": (settings.skeptic_model or settings.model, settings.native_budget.skeptic_seconds),
            "SCENARIO_ANALYST": (settings.scenario_model or settings.model, settings.native_budget.scenario_seconds),
            "DECISION_SYNTHESIZER": (settings.synthesis_model or settings.model, settings.native_budget.synthesis_seconds),
        }
        routes: dict[str, dict[str, Any]] = {}
        for role, (model, timeout) in defaults.items():
            configured: ModelRoutingPolicy | None = settings.models.get(role)
            routes[role] = {
                "model": configured.model if configured else model,
                "reasoning_effort": configured.reasoning_effort if configured else settings.reasoning_effort,
                "timeout_seconds": configured.timeout_seconds if configured else timeout,
                "max_attempts": configured.max_attempts if configured else 1,
            }
        return routes

    def run(
        self,
        request: DailyResearchInput,
        settings: ResearchSettings,
        *,
        mode: str = ShadowMode.SHADOW_LIVE,
        run_id: str | None = None,
        market_closed: bool = False,
    ) -> ShadowResearchRecord:
        if mode not in {ShadowMode.OFFLINE, ShadowMode.SHADOW_LIVE, ShadowMode.PRODUCTION_RESEARCH}:
            raise ValueError("SHADOW_MODE_INVALID")
        run_id = run_id or "shadow-" + uuid4().hex
        if mode == ShadowMode.SHADOW_LIVE and not settings.live_enabled:
            settings = settings.model_copy(update={"live_enabled": True})
        execution_state = "BLOCKED_MARKET_CLOSED" if market_closed else "BLOCKED_POLICY"
        routes = self.route(settings)
        runtime = self.orchestrator.runtime
        preflight: LiveModelPreflight | None = None
        if mode == ShadowMode.SHADOW_LIVE and isinstance(runtime, CodexResearchModelRuntime):
            preflight = runtime.preflight(routes)
        result = self.orchestrator.run(
            request,
            research_data_status="PASS" if request.freshness_status == "PASS" else "BLOCKED",
            execution_data_status="PASS" if request.freshness_status == "PASS" else "BLOCKED",
            execution_state=execution_state,  # type: ignore[arg-type]
            settings=settings,
            run_id=run_id,
            preflight_auth_blocked=bool(preflight and preflight.status == "AUTH_BLOCKED"),
        )
        quality = self.evaluator.evaluate(result)
        baseline_direction, baseline_confidence, baseline_ids = _deterministic_baseline(request)
        shadow_direction = result.synthesis.direction if result.synthesis else result.primary.direction if result.primary else "NEUTRAL"
        shadow_confidence = result.confidence.llm_self_confidence
        added: list[str] = []
        contradicted: list[str] = []
        if result.primary:
            added.extend(result.primary.key_drivers)
            if result.skeptic:
                added.extend(result.skeptic.challenges)
        if shadow_direction != baseline_direction:
            contradicted.append(f"direction:{baseline_direction}->{shadow_direction}")
        prior_direction = result.prior_memory.direction if result.prior_memory else None
        changed = (result.thesis_change.value,) if result.thesis_change.value != "UNCHANGED" else ()
        comparison = ResearchComparison(
            deterministic_direction=baseline_direction,
            deterministic_confidence=baseline_confidence,
            shadow_direction=shadow_direction,
            shadow_confidence=shadow_confidence,
            prior_direction=prior_direction,
            what_gpt_added=tuple(dict.fromkeys(added)),
            what_gpt_contradicted=tuple(contradicted),
            what_gpt_missed=(),
            what_deterministic_missed=tuple(item for item in (result.primary.key_drivers if result.primary else ()) if item not in baseline_ids),
            what_changed_from_prior=changed,
            disagreement=("HIGH" if result.disagreement_score >= 0.65 else "MODERATE" if result.disagreement_score >= 0.3 else "LOW"),
        )
        stages = {name: value.model_dump(mode="json") for name, value in result.stages.items()}
        confidence_value = result.confidence.system_confidence
        confidence_breakdown = dict(result.confidence.components)
        confidence_breakdown["grounding"] = quality.evidence_grounding_rate or 0.0
        confidence_breakdown["model_completion"] = quality.stage_completion_rate or 0.0
        confidence_breakdown["hallucination_penalty"] = -1.0 if quality.hallucinated_market_fact_count else 0.0
        if quality.hallucinated_market_fact_count:
            confidence_value = min(confidence_value, 0.35)
        elif quality.stage_completion_rate is not None and quality.stage_completion_rate < 0.75:
            confidence_value = min(confidence_value, 0.60)
        elif quality.unsupported_claim_rate is not None and quality.unsupported_claim_rate > 0.20:
            confidence_value = min(confidence_value, 0.50)
        valid_gpt_output = any(item.status.value == "SUCCESS" for item in result.stages.values())
        gpt_shadow_confidence = result.confidence.llm_self_confidence if valid_gpt_output else None
        combined_shadow_confidence = confidence_value if valid_gpt_output else None
        gpt_confidence_status = "AVAILABLE" if valid_gpt_output else "NOT_AVAILABLE"
        total_latency = quality.latency_ms
        record = ShadowResearchRecord(
            run_id=run_id,
            mode=mode,
            symbols=tuple(item.ticker for item in request.observations),
            evidence_count=len(result.evidence),
            model_route=routes,
            stages=stages,
            primary=result.primary.model_dump(mode="json") if result.primary else None,
            skeptic=result.skeptic.model_dump(mode="json") if result.skeptic else None,
            scenario=result.scenarios.model_dump(mode="json") if result.scenarios else None,
            synthesis=result.synthesis.model_dump(mode="json") if result.synthesis else None,
            system_confidence=confidence_value,
            deterministic_system_confidence=result.confidence.system_confidence,
            gpt_shadow_confidence=gpt_shadow_confidence,
            combined_shadow_confidence=combined_shadow_confidence,
            gpt_confidence_status=gpt_confidence_status,
            llm_self_confidence=result.confidence.llm_self_confidence,
            confidence_breakdown=confidence_breakdown,
            decision_state=result.decision_state.value,
            direction=shadow_direction,
            quality_metrics=quality,
            comparison=comparison,
            latency_ms=total_latency,
            usage_by_stage={name: value.usage for name, value in result.stages.items()},
            orders_created=0,
            orders_executed=0,
            live_preflight=preflight,
        )
        self._persist(record, request.analysis_cutoff)
        return record

    def _persist(self, record: ShadowResearchRecord, analysis_time: datetime) -> None:
        directory = self.paths.reports / analysis_time.date().isoformat() / record.run_id
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"shadow_research.{uuid4().hex}.tmp"
        target = directory / "shadow_research.json"
        temporary.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        calibration = self.paths.data / "research" / "calibration_log.jsonl"
        calibration.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "run_id": record.run_id,
            "date": analysis_time.isoformat(),
            "symbols": list(record.symbols),
            "evidence_count": record.evidence_count,
            "primary_status": record.stages.get("PRIMARY_ANALYST", {}).get("status"),
            "skeptic_status": record.stages.get("SKEPTIC", {}).get("status"),
            "scenario_status": record.stages.get("SCENARIO_ANALYSIS", {}).get("status"),
            "synthesis_status": record.stages.get("DECISION_SYNTHESIS", {}).get("status"),
            "system_confidence": record.system_confidence,
            "llm_self_confidence": record.llm_self_confidence,
            "direction": record.direction,
            "decision_state": record.decision_state,
            "unsupported_claim_rate": record.quality_metrics.unsupported_claim_rate,
            "grounding_rate": record.quality_metrics.evidence_grounding_rate,
            "hallucination_count": record.quality_metrics.hallucinated_market_fact_count,
            "disagreement_score": record.quality_metrics.analyst_skeptic_disagreement,
            "latency_ms": record.latency_ms,
            "model_route": record.model_route,
            "shadow_only": True,
        }
        with calibration.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")



def assess_promotion(records: Sequence[ShadowResearchRecord]) -> GPTResearchPromotionAssessment:
    """Conservative research-only promotion gate; it can never grant execution."""
    if not records:
        return GPTResearchPromotionAssessment(
            status=PromotionStatus.NOT_READY, reasons=("NO_SHADOW_RECORDS",)
        )
    completed = [
        record
        for record in records
        if record.quality_metrics.stage_completion_rate == 1.0
        and record.quality_metrics.hallucinated_market_fact_count == 0
        and record.quality_metrics.evidence_grounding_rate is not None
        and record.quality_metrics.evidence_grounding_rate >= 0.90
    ]
    if not completed:
        return GPTResearchPromotionAssessment(
            status=PromotionStatus.NOT_READY,
            reasons=("SCHEMA_OR_GROUNDING_TARGET_NOT_MET",),
        )
    if len(completed) < 3:
        return GPTResearchPromotionAssessment(
            status=PromotionStatus.SHADOW_ACCEPTABLE,
            reasons=("MORE_LIVE_SHADOW_SAMPLES_REQUIRED",),
        )
    return GPTResearchPromotionAssessment(
        status=PromotionStatus.CANDIDATE_FOR_PRODUCTION_RESEARCH,
        reasons=("SHADOW_QUALITY_TARGETS_MET", "RESEARCH_ONLY_NO_EXECUTION_AUTHORITY"),
    )

class RepeatabilityEvaluator:
    """Measure directional and confidence variance over repeated frozen runs."""

    def evaluate(self, records: Sequence[ShadowResearchRecord]) -> dict[str, Any]:
        if not records:
            return {"status": "UNKNOWN", "decision_consistency": None, "confidence_stddev": None}
        directions = [item.direction for item in records]
        confidences = [item.system_confidence for item in records if item.system_confidence is not None]
        return {
            "status": "KNOWN",
            "decision_consistency": max(directions.count(value) for value in set(directions)) / len(directions),
            "confidence_stddev": pstdev(confidences) if len(confidences) > 1 else 0.0,
            "core_claim_consistency": None,
            "runs": len(records),
        }


class ResearchEvaluationHarness:
    """Run deterministic fake-runtime fixture cases and aggregate metrics."""

    def evaluate(self, cases: Iterable[tuple[DailyResearchInput, ResearchSettings, GPTNativeResearchOrchestrator]]) -> dict[str, Any]:
        records: list[ShadowResearchRecord] = []
        for request, settings, orchestrator in cases:
            runner = ShadowResearchRunner(RuntimePaths(Path(".")), orchestrator=orchestrator)
            records.append(runner.run(request, settings, mode=ShadowMode.OFFLINE))
        metrics = [record.quality_metrics for record in records]
        values = [item.evidence_grounding_rate for item in metrics if item.evidence_grounding_rate is not None]

        def average(items: list[float]) -> float | None:
            return mean(items) if items else None
        return {
            "cases": len(records),
            "schema_success": average([item.schema_success_rate for item in metrics if item.schema_success_rate is not None]),
            "grounding": average(values),
            "unsupported_claims": average([item.unsupported_claim_rate for item in metrics if item.unsupported_claim_rate is not None]),
            "hallucinations": sum(item.hallucinated_market_fact_count for item in metrics),
            "average_latency": average([float(item.latency_ms) for item in metrics]),
            "p95_latency": max(item.latency_ms for item in metrics) if metrics else None,
            "records": [item.model_dump(mode="json") for item in records],
        }
