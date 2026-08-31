"""Tool-only, read-only MCP server for Meridian Alpha.

No tool authenticates to a broker, retrieves account data, or executes an order.
Without a verified production market-data adapter, non-zero accounts fail closed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse
from starlette.routing import Route

from meridian.audit import AuditStore
from meridian.config import load_policies
from meridian.execution_quote_providers import provider_preflight
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.host_readiness import evaluate_host_readiness
from meridian.orchestrator import DailyAnalysisService
from meridian.provider_registry import provider_certification_map
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState, RunStatus

ROOT = Path(__file__).parents[2]
STORE = AuditStore(ROOT / "var" / "meridian.db")
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
mcp = FastMCP(
    "Meridian Alpha",
    instructions=(
        "Meridian Alpha is decision support only. Never assume a recommended order filled. "
        "It has no brokerage execution capability."
    ),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool(
    title="Validate account snapshot",
    description="Use this after obtaining the user's current brokerage account snapshot from an authorized connected financial-data source.",
    annotations=READ_ONLY,
    structured_output=True,
)
def validate_account_snapshot(account_snapshot: AccountSnapshot) -> dict[str, Any]:
    """Validate a sanitized snapshot; no brokerage account number is required."""
    executable = (
        account_snapshot.sync_state is AccountSyncState.SYNCED
        and account_snapshot.freshness_state in {
            FreshnessState.VERIFIED,
            FreshnessState.RECENT,
        }
    )
    return {
        "valid": True,
        "snapshot_id": account_snapshot.snapshot_id,
        "freshness_state": account_snapshot.freshness_state,
        "executable_candidate": executable,
        "message": "Snapshot validated. Market data is separately required before a manual ticket can be ready.",
    }


@mcp.tool(
    title="Run daily analysis",
    description="Use this after validating a current AccountSnapshot from an authorized account-data source. It only calculates and never submits an order.",
    annotations=READ_ONLY,
    structured_output=True,
)
def run_daily_analysis(account_snapshot: AccountSnapshot, run_date: datetime) -> dict[str, Any]:
    """Run the shared application workflow; no provider means fail-closed market status."""
    decision = DailyAnalysisService(None, load_policies(ROOT / "policies")).run(
        account_snapshot, run_date
    )
    STORE.write_decision(decision)
    return decision.model_dump(mode="json")


@mcp.tool(
    title="Validate host account snapshot",
    description="Validate a sanitized HostAccountSnapshotEnvelope. This tool accepts no account numbers, credentials, or raw connector response.",
    annotations=READ_ONLY,
    structured_output=True,
)
def validate_host_account_snapshot(envelope: HostAccountSnapshotEnvelope) -> dict[str, Any]:
    snapshot = normalize_host_snapshot(envelope)
    gates = evaluate_host_readiness(snapshot)
    return {
        "valid": True,
        "snapshot_id": snapshot.snapshot_id,
        "coverage_status": envelope.coverage_status,
        "sync_state": snapshot.sync_state,
        "freshness_state": snapshot.freshness_state,
        "gates": [gate.model_dump(mode="json") for gate in gates],
        "manual_entry_eligible": any(
            gate.gate == "MANUAL_ENTRY_READY" and gate.status.value == "PASS" for gate in gates
        ),
        "readiness_blocker": "EXECUTION_QUOTE_AUTHORITY_UNAVAILABLE",
    }


@mcp.tool(
    title="Run host daily analysis",
    description="Run the same read-only daily-analysis service from a sanitized HostAccountSnapshotEnvelope. It never connects to an account source or submits an order.",
    annotations=READ_ONLY,
    structured_output=True,
)
def run_host_daily_analysis(envelope: HostAccountSnapshotEnvelope, run_date: datetime) -> dict[str, Any]:
    snapshot = normalize_host_snapshot(envelope)
    decision = DailyAnalysisService(None, load_policies(ROOT / "policies")).run(snapshot, run_date)
    STORE.write_decision(decision)
    return decision.model_dump(mode="json")


@mcp.tool(
    title="Get provider health",
    description="Return Meridian's declared provider capabilities and certification posture. This makes no network call.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_provider_health() -> dict[str, Any]:
    return {
        "providers": {
            name: certificate.model_dump(mode="json")
            for name, certificate in provider_certification_map().items()
        },
        "candidate_preflight": [
            item.model_dump(mode="json") for item in provider_preflight(probe=False)
        ],
        "execution_quote_authority": False,
    }

@mcp.tool(
    title="Get run",
    description="Use this to retrieve the sanitized audit summary for a prior Meridian run.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_run(run_id: str) -> dict[str, Any]:
    result = STORE.get_decision_summary(run_id)
    if result is None:
        return {"found": False, "run_id": run_id}
    return {"found": True, "result": result}


@mcp.tool(
    title="Get daily report",
    description="Return the sanitized report for one completed Meridian analysis run.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_daily_report(run_id: str) -> dict[str, Any]:
    return get_run(run_id)


@mcp.tool(
    title="Inspect evidence",
    description="Inspect only evidence identifiers retained in a sanitized run summary; no raw provider payloads are returned.",
    annotations=READ_ONLY,
    structured_output=True,
)
def inspect_evidence(run_id: str) -> dict[str, Any]:
    result = STORE.get_decision_summary(run_id)
    if result is None:
        return {"found": False, "run_id": run_id, "evidence_ids": []}
    return {"found": True, "run_id": run_id, "evidence_ids": [], "reason": "Raw evidence is not persisted in the default audit store."}


@mcp.tool(
    title="Inspect research",
    description="Inspect the sanitized research availability posture for a run without returning transcripts or credentials.",
    annotations=READ_ONLY,
    structured_output=True,
)
def inspect_research(run_id: str) -> dict[str, Any]:
    result = STORE.get_decision_summary(run_id)
    if result is None:
        return {"found": False, "run_id": run_id}
    return {"found": True, "run_id": run_id, "status": "SANITIZED_AUDIT_ONLY", "transcript_available": False}


@mcp.tool(
    title="Inspect target portfolio",
    description="Return deterministic target weights from a sanitized run summary.",
    annotations=READ_ONLY,
    structured_output=True,
)
def inspect_target_portfolio(run_id: str) -> dict[str, Any]:
    result = STORE.get_decision_summary(run_id)
    if result is None:
        return {"found": False, "run_id": run_id, "target": []}
    return {"found": True, "run_id": run_id, "target": result.get("recommendations", [])}


@mcp.tool(
    title="Inspect manual draft",
    description="Return a manual draft only when deterministic readiness gates pass; never submits it.",
    annotations=READ_ONLY,
    structured_output=True,
)
def inspect_manual_draft(run_id: str) -> dict[str, Any]:
    return get_order_ticket(run_id)


@mcp.tool(
    title="Provider health",
    description="Alias for the read-only provider capability and health report.",
    annotations=READ_ONLY,
    structured_output=True,
)
def provider_health() -> dict[str, Any]:
    return get_provider_health()


@mcp.tool(
    title="Get order ticket",
    description="Use this to retrieve a manual order ticket only when a run is already READY_FOR_MANUAL_ENTRY.",
    annotations=READ_ONLY,
    structured_output=True,
)
def get_order_ticket(run_id: str) -> dict[str, Any]:
    result = STORE.get_decision_summary(run_id)
    if result is None:
        return {"found": False, "ticket_available": False, "reason": "Unknown run."}
    run = result["run"]
    if not isinstance(run, dict):
        raise RuntimeError("Invalid sanitized audit record")
    status = str(run["overall_status"])
    if status != RunStatus.READY_FOR_MANUAL_ENTRY:
        return {
            "found": True,
            "ticket_available": False,
            "status": status,
            "reason": "DRAFT — DO NOT ENTER",
        }
    return {"found": True, "ticket_available": True, "status": status, "orders": result["orders"]}


@mcp.tool(
    title="Explain decision",
    description="Use this to explain a sanitized Meridian decision and its safety status without creating or changing any order.",
    annotations=READ_ONLY,
    structured_output=True,
)
def explain_decision(run_id: str) -> dict[str, Any]:
    result = STORE.get_decision_summary(run_id)
    if result is None:
        return {"found": False, "explanation": "No run with that identifier exists."}
    run = result["run"]
    recommendations = result["recommendations"]
    orders = result["orders"]
    if (
        not isinstance(run, dict)
        or not isinstance(recommendations, list)
        or not isinstance(orders, list)
    ):
        raise RuntimeError("Invalid sanitized audit record")
    return {
        "found": True,
        "status": run["overall_status"],
        "explanation": "This is decision support only. A later AccountSnapshot, not this run, determines whether any manual order filled.",
        "recommendation_count": len(recommendations),
        "order_count": len(orders),
    }


async def health(_: Any) -> JSONResponse:
    return JSONResponse(
        {"status": "ok", "service": "meridian-alpha", "execution_capability": False}
    )


app = mcp.streamable_http_app()
app.routes.append(Route("/health", health))


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)
