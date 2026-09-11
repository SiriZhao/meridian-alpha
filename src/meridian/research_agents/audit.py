"""Strictly allowlisted research audit artifacts; no account payload is accepted."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_research_audit(
    root: Path,
    run_id: str,
    *,
    research: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, str]:
    """Persist status/hashes only; this function has no account-snapshot parameter."""
    context = research.get("context")
    context = context if isinstance(context, dict) else {}
    response = research.get("structured_response")
    response = response if isinstance(response, dict) else {}
    preparation = research.get("preparation_diagnostics")
    preparation = preparation if isinstance(preparation, dict) else {}
    directory = root / run_id
    try:
        directory.mkdir(parents=True, exist_ok=True)
        research_path = directory / "final_research.json"
        decision_path = directory / "decision.json"
        research_payload = {
            "research_run_id": context.get("research_run_id"),
            "input_hash": context.get("input_hash"),
            "research_status": context.get("status"),
            "provider": research.get("provider"),
            "model": research.get("model"),
            "error_code": research.get("error_code"),
            "response_status": response.get("status"),
            "recommended_action": response.get("recommended_action"),
            "confidence": response.get("confidence"),
            "data_gaps": response.get("data_gaps", []),
            "data_status": preparation.get("status"),
            "quality_score": preparation.get("quality_score"),
            "quality_grade": preparation.get("quality_grade"),
            "source_count": preparation.get("source_count"),
            "blocking_missing": preparation.get("blocking_missing", []),
            "raw_account_persisted": False,
        }
        decision_payload = {
            "run_id": decision.get("run_id"),
            "as_of": decision.get("as_of"),
            "overall_status": decision.get("overall_status"),
            "blocked_reasons": decision.get("blocked_reasons", []),
            "order_count": len(decision.get("orders", []))
            if isinstance(decision.get("orders"), list)
            else 0,
            "broker_submission": "DISABLED",
            "raw_account_persisted": False,
        }
        research_path.write_text(
            json.dumps(research_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        decision_path.write_text(
            json.dumps(decision_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        return {"final_research": str(research_path), "decision": str(decision_path)}
    except OSError:
        return {}
