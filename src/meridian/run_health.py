"""Best-effort per-run health receipts with no trading authority."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from meridian.runtime import RuntimePaths

STAGES = (
    "PRE_FLIGHT",
    "MARKET_QUOTE",
    "HISTORICAL_DATA",
    "BENCHMARK_DATA",
    "DATA_VALIDATION",
    "RESEARCH",
    "DECISION",
    "PORTFOLIO",
    "PAPER_EXECUTION",
    "REPORT_GENERATION",
    "REPORT_PERSISTENCE",
    "RUN_FINALIZATION",
)


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
    now = datetime.now(UTC).isoformat()
    started = str(payload.get("analysis_time") or now)
    raw_stages = payload.get("stages", [])
    observed: dict[str, dict[str, object]] = {}
    if isinstance(raw_stages, list):
        for item in raw_stages:
            if isinstance(item, dict):
                observed[str(item.get("stage", "")).upper()] = item
    aliases = {
        "MARKET_QUOTE": "MARKET",
        "HISTORICAL_DATA": "MARKET",
        "BENCHMARK_DATA": "MARKET",
        "DATA_VALIDATION": "MARKET",
        "PORTFOLIO": "DECISION",
    }
    is_paper = bool(payload.get("paper_run_id"))
    canonical_run_id = str(payload.get("canonical_run_id") or "") or None
    stages = []
    for name in STAGES:
        source = observed.get(name) or observed.get(aliases.get(name, ""))
        if source:
            begin = str(source.get("start") or started)
            end = str(source.get("finish") or now)
            status = str(source.get("status") or "UNKNOWN")
            error = source.get("error_code")
            stages.append(
                _stage(
                    name,
                    begin,
                    end,
                    status,
                    str(error) if error else None,
                    stage_source=("CANONICAL_RUN" if is_paper else None),
                    source_run_id=(canonical_run_id if is_paper else None),
                )
            )
        else:
            if is_paper and canonical_run_id:
                stages.append(
                    _stage(
                        name,
                        started,
                        now,
                        "INHERITED",
                        stage_source="CANONICAL_RUN",
                        source_run_id=canonical_run_id,
                    )
                )
            else:
                status = (
                    "PASS"
                    if name in {"REPORT_GENERATION", "REPORT_PERSISTENCE", "RUN_FINALIZATION"}
                    else "NOT_RECORDED"
                )
                stages.append(_stage(name, started, now, status))
    probes = payload.get("provider_probes", {})
    probes = probes if isinstance(probes, dict) else {}
    research = payload.get("research", {})
    research = research if isinstance(research, dict) else {}
    blockers = payload.get("blocked_reasons", payload.get("blockers", []))
    blockers = blockers if isinstance(blockers, list) else []
    orders = payload.get("orders", [])
    orders = orders if isinstance(orders, list) else []
    paper = payload.get("paper_execution", {})
    paper = paper if isinstance(paper, dict) else {}
    market = payload.get("market", {})
    market = market if isinstance(market, dict) else {}
    decision = payload.get("decision", {})
    decision = decision if isinstance(decision, dict) else {}
    cache = payload.get("cache", {})
    cache = cache if isinstance(cache, dict) else {}
    finished = datetime.now(UTC)
    try:
        duration_ms = max(
            0, round((finished - datetime.fromisoformat(started)).total_seconds() * 1000)
        )
    except ValueError:
        duration_ms = 0
    result = {
        "schema_version": "meridian-run-health.v1",
        "run_id": str(payload.get("run_id") or payload.get("paper_run_id") or "UNKNOWN"),
        "started_at": started,
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
        "overall_status": payload.get("status", "ERROR"),
        "stages": stages,
        "market_data": {
            "status": payload.get(
                "data_status",
                market.get("status", "UNKNOWN"),
            ),
            "symbols": probes,
            "providers_attempted": [],
            "providers_used": [],
            "fallbacks_used": [],
            "warnings": [],
        },
        "research": {
            "status": payload.get("research_status", research.get("status", "NOT_RUN")),
            "research_mode": research.get("research_mode", "OFFLINE_RESEARCH"),
            "research_confidence": research.get("research_confidence"),
            "llm_available": research.get("llm_available", False),
            "fallback_reason": research.get("fallback_reason"),
        },
        "decision": {
            "status": decision.get("status", payload.get("status")),
            "blocking_reason": blockers[0] if blockers else None,
            "orders_created": len(orders),
        },
        "paper_execution": {
            "status": paper.get("status", "NOT_RUN"),
            "orders_executed": len(paper.get("fills", []))
            if isinstance(paper.get("fills", []), list)
            else 0,
        },
        "cache": {
            "reads": 0,
            "writes": 0,
            "hits": sum(1 for value in cache.values() if value),
            "misses": 0,
            "stale_rejected": 0,
        },
        "warnings": payload.get("warnings", []),
        "errors": payload.get("errors", []),
        "blocking_reason": blockers[0] if blockers else None,
        "execution_authority": "NONE",
    }
    if is_paper and canonical_run_id:
        result["canonical_run_id"] = canonical_run_id
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
        try:
            os.replace(temporary, destination)
        except OSError as error:
            # Some Windows encrypted runtime volumes reject ReplaceFile across
            # their virtualized backing store (WinError 17). Preserve the
            # receipt with a flushed copy rather than silently losing health.
            if getattr(error, "winerror", None) != 17:
                raise
            with temporary.open("rb") as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            temporary.unlink(missing_ok=True)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
