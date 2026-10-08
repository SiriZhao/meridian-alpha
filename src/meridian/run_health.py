"""Best-effort per-run health receipts with no trading authority."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from meridian.canonical_run import canonical_snapshot, first, mapping, optional_text, sequence
from meridian.daily_closure import publish_staged_report
from meridian.runtime import RuntimePaths

STAGES = (
    "PRE_FLIGHT",
    "MARKET_QUOTE",
    "HISTORICAL_DATA",
    "BENCHMARK_DATA",
    "DATA_VALIDATION",
    "RESEARCH",
    "PRIMARY_ANALYST",
    "SKEPTIC",
    "SCENARIO_ANALYSIS",
    "DECISION_SYNTHESIS",
    "DECISION",
    "PORTFOLIO",
    "PAPER_EXECUTION",
)


class WorkflowStageStatus(StrEnum):
    """Stable lifecycle vocabulary used by canonical and paper reports."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    SKIPPED = "SKIPPED"
    INHERITED = "INHERITED"


def _stage(
    name: str,
    started: str,
    finished: str,
    status: str,
    error: str | None = None,
    *,
    stage_source: str | None = None,
    source_run_id: str | None = None,
) -> dict[str, object]:
    try:
        elapsed = max(
            0,
            round(
                (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
                * 1000
            ),
        )
    except ValueError:
        elapsed = 0
    result: dict[str, object] = {
        "name": name,
        "started_at": started,
        "finished_at": finished,
        "elapsed_ms": elapsed,
        "status": status,
        "error_type": error,
        "error_message": error,
    }
    if stage_source is not None:
        result["stage_source"] = stage_source
    if source_run_id is not None:
        result["source_run_id"] = source_run_id
    return result


def build_run_health(payload: dict[str, object]) -> dict[str, object]:
    """Project the canonical business state and recorded receipt timings only."""
    canonical = canonical_snapshot(payload)
    now = datetime.now(UTC).isoformat()
    started = str(payload.get("analysis_time") or now)
    observed = {str(item.get("stage", "")).upper(): item
                for item in sequence(payload.get("stages")) if isinstance(item, dict)}
    native_stages = mapping(canonical.research.intelligence.get("stages"))
    truth = {stage.name: stage for stage in canonical.stages}
    stages = []
    for name in dict.fromkeys((*STAGES, *truth)):
        fact = truth.get(name)
        source = observed.get(name, {})
        native = mapping(native_stages.get(name))
        stage = _stage(name, str(source.get("start") or started),
            str(source.get("finish") or started),
            fact.result_status if fact else "NOT_RECORDED",
            optional_text(first(source.get("error_code"), native.get("error_type"))),
            stage_source=fact.source if fact else "UNRECORDED",
            source_run_id=fact.source_run_id if fact else None)
        stage.update({"execution_state": fact.execution_state.value if fact else "UNKNOWN",
                      "result_status": fact.result_status if fact else "UNKNOWN",
                      "source_run_id": fact.source_run_id if fact else None})
        if native:
            timing = mapping(native.get("diagnostic"))
            shared = timing.get("shared_invocation") is True
            stage.update({"elapsed_ms": None if shared else native.get("duration_ms"), "model": native.get("model"),
                          "shared_invocation_id": timing.get("shared_invocation_id"),
                          "shared_invocation_wall_ms": native.get("duration_ms") if shared else None,
                          "logical_participation": True,
                          "role_configured_budget_seconds": timing.get("role_configured_budget_seconds"),
                          "duration_semantics": "NON_ADDITIVE_SHARED_PROCESS" if shared else "INDEPENDENT_PROCESS",
                          "schema_valid": native.get("schema_valid")})
        stages.append(stage)
    intelligence = canonical.research.intelligence
    claims = sequence(intelligence.get("claims"))
    paper = canonical.execution
    research = canonical.research
    market = canonical.market
    elapsed = payload.get("elapsed_seconds")
    # Do not claim cache misses, writes, finalization or persistence success
    # where the canonical producer recorded no measurement.
    result: dict[str, object] = {
        "schema_version": "meridian-run-health.v1",
        "run_id": canonical.run_id,
        "canonical_run_id": canonical.canonical_run_id,
        "canonical_state": canonical.model_dump(mode="json"),
        "trading_date": canonical.trading_date, "account": canonical.account,
        "started_at": started, "finished_at": payload.get("finished_at"), "projected_at": now,
        "duration_ms": round(elapsed * 1000) if isinstance(elapsed, (float, int)) else None,
        "overall_status": canonical.result_status, "stages": stages,
        "portfolio": {"nav": canonical.nav, "cash": canonical.cash, "position_count": canonical.position_count},
        "market_data": {"status": market.result_status, "session": market.session,
            "symbols": market.provider_probes, "providers_attempted": list(market.providers_attempted),
            "providers_used": list(market.providers_used), "fallbacks_used": list(market.fallbacks_used),
            "quote_certification": market.quote_certification, "warnings": sequence(payload.get("warnings"))},
        "research": {"status": research.result_status, "execution_state": research.execution_state.value,
            "research_mode": research.mode, "research_confidence": research.confidence,
            "llm_available": research.llm_available, "fallback_reason": research.fallback_reason,
            "research_state": research.research_state,
            "research_data_status": intelligence.get("research_data_status"),
            "evidence_count": len(sequence(intelligence.get("evidence"))),
            "supported_claims": sum(1 for c in claims if mapping(c).get("status") == "SUPPORTED"),
            "conflicted_claims": sum(1 for c in claims if mapping(c).get("status") == "CONFLICTED"),
            "system_confidence": mapping(intelligence.get("confidence")).get("system_confidence")},
        "decision": {"status": canonical.decision.result_status,
            "attribution": canonical.decision.attribution,
            "orders_created": canonical.decision.order_count,
            "blocking_reason": canonical.blockers[0] if canonical.blockers else None,
            "decision_state": intelligence.get("decision_state")},
        "paper_execution": {"status": paper.result_status, "execution_state": paper.execution_state.value,
            "orders_executed": paper.fill_count, "intent_count": paper.order_count, "authority": paper.authority},
        "cache": {"reads": None, "writes": None, "hits": None, "misses": None, "stale_rejected": None},
        "warnings": sequence(payload.get("warnings")), "errors": sequence(payload.get("errors")),
        "blocking_reason": canonical.blockers[0] if canonical.blockers else None,
        "execution_authority": "NONE", "broker_submission": paper.broker_submission,
        "broker_side_effects": paper.broker_side_effects,
        "execution_state": intelligence.get("execution_state"),
        "execution_data_status": intelligence.get("execution_data_status"),
        "idempotency": payload.get("idempotency"),
        "idempotency_state": canonical.idempotency.model_dump(mode="json"),
        "status_dimensions": canonical.status_dimensions,
        "readiness": canonical.readiness,
        "forward_evidence": canonical.forward_evidence,
        "manual_authority": canonical.manual_authority,
    }
    if canonical.paper_run_id:
        result["stage_source"] = "CANONICAL_RUN"
    return result


def persist_run_health(payload: dict[str, object], paths: RuntimePaths) -> Path:
    health = build_run_health(payload)
    as_of = datetime.fromisoformat(
        str(payload.get("analysis_time") or datetime.now(UTC).isoformat())
    )
    run_id = str(health["run_id"])
    directory = paths.reports / as_of.date().isoformat() / run_id
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "run_health.json"
    temporary = directory / f"run_health.{uuid4().hex}.tmp"
    data = (
        json.dumps(health, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    ).encode()
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        publish_staged_report(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
