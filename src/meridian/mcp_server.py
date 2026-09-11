"""Tool-only, read-only MCP server for Meridian Alpha.

No tool authenticates to a broker, retrieves account data, or executes an order.
Without a verified production market-data adapter, non-zero accounts fail closed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse
from starlette.routing import Route

from meridian.analytics.derived_market_features import derive_market_features
from meridian.application import MeridianApplicationService
from meridian.audit import AuditStore
from meridian.config import load_policies
from meridian.daily_closure import DailyClosureService
from meridian.data.models import ResearchEvidencePackage
from meridian.event_evidence import QualitativeEventEvidence
from meridian.evidence_foundation import MacroObservation
from meridian.execution_quote_providers import provider_preflight
from meridian.fundamentals import (
    certified_company_snapshot,
)
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.host_readiness import evaluate_host_readiness
from meridian.macro_context import compact_macro_context
from meridian.market import Bar
from meridian.operational_data import FreshnessPolicy
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.provider_registry import provider_certification_map
from meridian.runtime import RuntimePaths, policy_directory
from meridian.runtime_diagnostics import report
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    FreshnessState,
    MarketSnapshot,
    RunStatus,
)

ROOT = Path(__file__).parents[2]

def _service() -> MeridianApplicationService:
    return MeridianApplicationService()


def _store() -> AuditStore:
    return AuditStore(RuntimePaths.from_environment().db)
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

ASTRA_TOOL_NAMES = frozenset({
    "runtime_status", "market_snapshot", "account_snapshot", "company_facts",
    "event_evidence", "macro_context", "research_packet", "quant_metrics", "portfolio_context", "risk_analysis",
    "forward_evidence", "daily_closure", "audit_lookup",
})


def registered_tool_names() -> frozenset[str]:
    """Return the names actually registered with FastMCP."""
    tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
    return frozenset(str(name) for name in tools)


def _tool_metadata(*, source: str, observed_at: datetime | None,
                   analysis_cutoff: datetime | None, freshness: str,
                   data_quality: str, provenance: str,
                   errors: list[str] | None = None,
                   warnings: list[str] | None = None, known_at: datetime | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "known_at": known_at.isoformat() if known_at else None,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "analysis_cutoff": analysis_cutoff.isoformat() if analysis_cutoff else None,
        "freshness": freshness,
        "data_quality": data_quality,
        "provenance": provenance,
        "errors": errors or [],
        "warnings": warnings or [],
        "execution_authority": "NONE",
    }
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
    errors: list[str] = []
    if account_snapshot.freshness_state not in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
        errors.append("ACCOUNT_SNAPSHOT_STALE")
    if account_snapshot.sync_state is not AccountSyncState.SYNCED:
        errors.append("ACCOUNT_SNAPSHOT_NOT_SYNCED")
    return {
        "valid": not errors,
        "snapshot_id": account_snapshot.snapshot_id,
        "freshness_state": account_snapshot.freshness_state,
        "executable_candidate": False,
        "errors": errors,
        "execution_authority": "NONE",
        "message": "Snapshot validation never grants execution authority; market, evidence, risk, reconciliation, quote certification, and human approval remain required.",
    }


def run_daily_analysis(account_snapshot: AccountSnapshot, run_date: datetime) -> dict[str, Any]:
    """Retired: a canonical daily run requires an envelope and its provenance."""
    _ = account_snapshot, run_date
    return {"status": "BLOCKED", "error_code": "CANONICAL_HOST_ENVELOPE_REQUIRED",
            "next_action": "Use run_host_daily_analysis with a fresh sanitized HostAccountSnapshotEnvelope.",
            "broker_submission": "DISABLED"}


@mcp.tool(
    title="Validate host account snapshot",
    description="Validate a sanitized HostAccountSnapshotEnvelope. This tool accepts no account numbers, credentials, or raw connector response.",
    annotations=READ_ONLY,
    structured_output=True,
)
def validate_host_account_snapshot(envelope: HostAccountSnapshotEnvelope) -> dict[str, Any]:
    snapshot = normalize_host_snapshot(envelope)
    gates = evaluate_host_readiness(snapshot)
    account_gate = next(gate for gate in gates if gate.gate == "ACCOUNT_READY")
    errors = [] if account_gate.status.value == "PASS" else [
        "ACCOUNT_SNAPSHOT_STALE" if snapshot.freshness_state in {FreshnessState.STALE, FreshnessState.UNKNOWN}
        else "ACCOUNT_SNAPSHOT_NOT_READY"
    ]
    return {
        "valid": not errors,
        "snapshot_id": snapshot.snapshot_id,
        "coverage_status": envelope.coverage_status,
        "sync_state": snapshot.sync_state,
        "freshness_state": snapshot.freshness_state,
        "gates": [gate.model_dump(mode="json") for gate in gates],
        "manual_entry_eligible": any(
            gate.gate == "MANUAL_ENTRY_READY" and gate.status.value == "PASS" for gate in gates
        ),
        "readiness_blocker": "EXECUTION_QUOTE_AUTHORITY_UNAVAILABLE",
        "errors": errors,
        "execution_authority": "NONE",
    }


def run_host_daily_analysis(envelope: HostAccountSnapshotEnvelope, run_date: datetime) -> dict[str, Any]:
    """Run the one canonical application path using a short-lived envelope file."""
    _ = run_date  # Canonical daily binds its own UTC cutoff; caller time cannot override it.
    service = _service()
    service.paths.ensure_directories()
    temporary = service.paths.cache / "mcp-snapshots" / ("host-" + uuid4().hex + ".json")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    try:
        return service.daily(temporary)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


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
    result = _store().get_decision_summary(run_id)
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
    result = _store().get_decision_summary(run_id)
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
    result = _store().get_decision_summary(run_id)
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
    result = _store().get_decision_summary(run_id)
    if result is None:
        return {"found": False, "run_id": run_id, "target": []}
    return {"found": True, "run_id": run_id, "target": result.get("recommendations", [])}


@mcp.tool(
    title="Inspect portfolio target",
    description="Return the deterministic target portfolio from a sanitized run summary.",
    annotations=READ_ONLY,
    structured_output=True,
)
def inspect_portfolio_target(run_id: str) -> dict[str, Any]:
    """V1 name for target inspection; read-only alias of inspect_target_portfolio."""
    return inspect_target_portfolio(run_id)
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
    result = _store().get_decision_summary(run_id)
    if result is None:
        return {"found": False, "ticket_available": False, "reason": "Unknown run."}
    run = result["run"]
    if not isinstance(run, dict):
        raise RuntimeError("Invalid sanitized audit record")
    status = str(run["overall_status"])
    certificate = result.get("manual_readiness_certificate")
    if status != RunStatus.READY_FOR_MANUAL_ENTRY:
        return {
            "found": True,
            "ticket_available": False,
            "status": status,
            "reason": "DRAFT — DO NOT ENTER",
        }
    if not isinstance(certificate, dict) or str(certificate.get("status")) != "READY":
        return {"found": True, "ticket_available": False, "status": status, "reason": "BLOCKED_MANUAL_READINESS_CERTIFICATE_REQUIRED"}
    orders = result.get("orders")
    if not isinstance(orders, list) or not orders or any(
        not isinstance(order, dict)
        or str(order.get("status")) != "NOT_EXECUTED"
        or not order.get("quote_certificate_id")
        for order in orders
    ):
        return {
            "found": True,
            "ticket_available": False,
            "status": status,
            "reason": "BLOCKED_MANUAL_ORDER_DRAFT_NOT_SEALED",
        }
    return {"found": True, "ticket_available": True, "status": status, "orders": orders, "manual_readiness_certificate": certificate}


@mcp.tool(
    title="Explain decision",
    description="Use this to explain a sanitized Meridian decision and its safety status without creating or changing any order.",
    annotations=READ_ONLY,
    structured_output=True,
)
def explain_decision(run_id: str) -> dict[str, Any]:
    result = _store().get_decision_summary(run_id)
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


# Astra-native capability surface.  These wrappers expose typed, deterministic
# Meridian capabilities; they do not call a second reasoning model.
@mcp.tool(title="Runtime status", annotations=READ_ONLY, structured_output=True)
def runtime_status() -> dict[str, Any]:
    payload = report(RuntimePaths.from_environment(), probe_writes=False)
    return {**payload, **_tool_metadata(
        source="meridian-runtime-diagnostics", observed_at=None, analysis_cutoff=None,
        freshness="CURRENT", data_quality=str(payload.get("status", "UNKNOWN")),
        provenance="RuntimePaths + local dependency/Codex/MCP diagnostics",
    )}


@mcp.tool(title="Market snapshot", annotations=READ_ONLY, structured_output=True)
def market_snapshot(symbols: list[str], analysis_cutoff: datetime) -> dict[str, Any]:
    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        return _tool_metadata(source="operational-market", observed_at=None,
                              analysis_cutoff=None, freshness="UNKNOWN",
                              data_quality="REJECTED", provenance="none",
                              errors=["ANALYSIS_TIME_TIMEZONE_REQUIRED"])
    policies = load_policies(policy_directory())
    snapshot = OperationalMarketSnapshotService.from_runtime(
        RuntimePaths.from_environment(),
        policy=FreshnessPolicy(quote_max_age_seconds=policies.data.quote_max_age_seconds,
                               account_max_age_seconds=policies.data.account_snapshot_max_age_seconds),
    ).build(symbols, analysis_time=analysis_cutoff, live=True)
    quotes = {key: value for key, value in snapshot.research_quotes.items() if value.timestamp <= analysis_cutoff}
    excluded = set(snapshot.research_quotes) - set(quotes)
    errors = [*snapshot.missing_symbols.values(), *[f"QUOTE_AFTER_CUTOFF:{key}" for key in sorted(excluded)]]
    return {
        "status": "REJECTED" if excluded else snapshot.status,
        "quotes": {key: value.model_dump(mode="json") for key, value in quotes.items()},
        "missing_symbols": snapshot.missing_symbols,
        "provider_probes": snapshot.provider_probes,
        "collection_completed_at": snapshot.analysis_time.isoformat(),
        **_tool_metadata(source="operational-market-provider-chain",
                         observed_at=max((item.timestamp for item in quotes.values()), default=None),
                         analysis_cutoff=analysis_cutoff,
                         freshness="FRESH" if snapshot.status == "OPERATIONAL_READY" else "STALE_OR_UNAVAILABLE",
                         data_quality=snapshot.data_quality_mode,
                         provenance=snapshot.snapshot_hash,
                         errors=errors, warnings=["PUBLIC_RESEARCH_DATA_NOT_HISTORICAL_PIT_CERTIFIED"]),
    }


@mcp.tool(title="Account snapshot", annotations=READ_ONLY, structured_output=True)
def account_snapshot(account: AccountSnapshot, analysis_cutoff: datetime) -> dict[str, Any]:
    errors: list[str] = []
    if account.as_of > analysis_cutoff:
        errors.append("ACCOUNT_AFTER_CUTOFF")
    elif (analysis_cutoff - account.as_of).total_seconds() > load_policies(policy_directory()).data.account_snapshot_max_age_seconds and account.freshness_state in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
        errors.append("ACCOUNT_SNAPSHOT_STALE")
    if account.freshness_state not in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
        errors.append("ACCOUNT_SNAPSHOT_STALE")
    if account.sync_state is not AccountSyncState.SYNCED:
        errors.append("ACCOUNT_SNAPSHOT_NOT_SYNCED")
    return {
        "valid": not errors,
        "snapshot_id": account.snapshot_id,
        "sync_state": account.sync_state.value,
        "freshness_state": account.freshness_state.value,
        **_tool_metadata(source="authorized-sanitized-account-snapshot",
                         observed_at=account.as_of, analysis_cutoff=analysis_cutoff,
                         freshness=account.freshness_state.value,
                         data_quality="PASS" if not errors else "REJECTED",
                         provenance="AccountSnapshot contract; raw account identifier absent",
                         errors=errors),
    }



def _fundamental_trends(snapshot: Any) -> dict[str, Any]:
    """Machine-readable deterministic trend facts; no LLM interpretation."""
    trend_metrics = {
        "revenue_growth_trend": "REVENUE",
        "operating_income_trend": "OPERATING_INCOME",
        "fcf_trend": "FREE_CASH_FLOW",
        "capex_trend": "CAPEX",
        "share_count_trend": "SHARES_OUTSTANDING",
        "cash_debt_trend": "CASH_AND_EQUIVALENTS",
    }
    comparisons = {item.metric.value: item for item in snapshot.comparable_series}
    result: dict[str, Any] = {}
    for name, metric in trend_metrics.items():
        item = comparisons.get(metric)
        if item is None or item.yoy_change is None:
            result[name] = {"status": "UNKNOWN", "reason": "NO_COMPARABLE_CERTIFIED_PERIOD"}
            continue
        direction = "INCREASING" if item.yoy_change > 0 else "DECREASING" if item.yoy_change < 0 else "STABLE"
        result[name] = {
            "status": "AVAILABLE",
            "direction": direction,
            "yoy_change": str(item.yoy_change),
            "current_fact_id": item.current_fact_id,
            "prior_fact_id": item.prior_fact_id,
        }
    return result


@mcp.tool(title="Company facts", annotations=READ_ONLY, structured_output=True)
def company_facts(symbol: str, analysis_cutoff: datetime) -> dict[str, Any]:
    """Certified, point-in-time SEC fundamentals for Astra research only."""
    try:
        numeric, snapshot = certified_company_snapshot(symbol, analysis_cutoff)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": "UNAVAILABLE", "facts": [], **_tool_metadata(
            source="sec-edgar-companyfacts-and-submissions", observed_at=None,
            analysis_cutoff=analysis_cutoff, freshness="UNKNOWN", data_quality="MISSING",
            provenance="SEC Company Facts + exact submissions acceptance metadata",
            errors=[str(error) or type(error).__name__],
        )}
    if not snapshot.facts:
        return {"status": "UNAVAILABLE", "facts": [], **_tool_metadata(
            source="sec-edgar-companyfacts-and-submissions", observed_at=None,
            analysis_cutoff=analysis_cutoff, freshness="UNKNOWN", data_quality="MISSING",
            provenance="SEC Company Facts + exact submissions acceptance metadata",
            errors=["CERTIFIED_FUNDAMENTAL_DATA_MISSING", *numeric.last_exclusions[:20]],
        )}
    identity = numeric.last_identity or (None, None, None, None)
    latest = snapshot.latest_accepted_at
    valuation = {
        "market_cap": {"status": "NOT_AVAILABLE", "reason": "CURRENT_CERTIFIED_MARKET_PRICE_REQUIRED"},
        "enterprise_value": {"status": "NOT_AVAILABLE", "reason": "CURRENT_CERTIFIED_MARKET_PRICE_REQUIRED"},
        "pe": {"status": "NOT_AVAILABLE", "reason": "CURRENT_CERTIFIED_MARKET_PRICE_REQUIRED"},
        "forward_pe": {"status": "NOT_AVAILABLE", "reason": "NO_SOURCED_FORWARD_ESTIMATE"},
        "ps": {"status": "NOT_AVAILABLE", "reason": "CURRENT_CERTIFIED_MARKET_PRICE_REQUIRED"},
        "ev_sales": {"status": "NOT_AVAILABLE", "reason": "CURRENT_CERTIFIED_MARKET_PRICE_REQUIRED"},
        "ev_ebitda": {"status": "NOT_AVAILABLE", "reason": "SOURCED_EBITDA_AND_MARKET_PRICE_REQUIRED"},
        "fcf_yield": {"status": "NOT_AVAILABLE", "reason": "CURRENT_CERTIFIED_MARKET_PRICE_REQUIRED"},
    }
    return {
        "status": "AVAILABLE" if not snapshot.quality_flags else "DATA_DEGRADED",
        "identity": {"ticker": symbol.upper(), "company_name": identity[1], "cik": identity[0],
                     "exchange": identity[2], "resolution_source": "SEC company_tickers.json",
                     "resolved_at": identity[3].isoformat() if identity[3] else None},
        "facts": [fact.model_dump(mode="json") for fact in snapshot.facts],
        "comparable_facts": [fact.model_dump(mode="json") for fact in snapshot.comparable_facts],
        "quarterly_history": [fact.model_dump(mode="json") for fact in snapshot.quarterly_history],
        "component_facts": [fact.model_dump(mode="json") for fact in snapshot.component_facts],
        "financial_history": [item.model_dump(mode="json") for item in snapshot.comparable_series],
        "derived_metrics": [item.model_dump(mode="json") for item in snapshot.derived],
        "trends": _fundamental_trends(snapshot),
        "valuation_context": valuation,
        "filing_provenance": {
            "latest_accession": snapshot.latest_accession, "latest_form": snapshot.latest_form,
            "latest_accepted_at": latest.isoformat() if latest else None,
            "source_hashes": list(snapshot.source_hashes), "restatement_status": snapshot.restatement_status,
            "excluded": list(snapshot.excluded), "missing_metrics": list(snapshot.missing_metrics),
        },
        **_tool_metadata(source="SEC EDGAR: Company Facts + submissions acceptance metadata",
                         observed_at=latest, known_at=latest, analysis_cutoff=analysis_cutoff,
                         freshness="AS_OF_CUTOFF", data_quality="PASS" if not snapshot.quality_flags else "DEGRADED",
                         provenance=snapshot.content_hash,
                         warnings=list(snapshot.quality_flags), errors=[]),
    }

@mcp.tool(title="Event evidence", annotations=READ_ONLY, structured_output=True)
def event_evidence(events: list[QualitativeEventEvidence], analysis_cutoff: datetime) -> dict[str, Any]:
    """Return source-bound qualitative events only; no market-value authority."""
    valid = list({item.event_id: item for item in events if item.published_at <= analysis_cutoff}.values())[:100]
    excluded = sum(item.published_at > analysis_cutoff for item in events)
    return {
        "status": "AVAILABLE" if valid else "UNAVAILABLE",
        "events": [item.model_dump(mode="json") for item in valid],
        **_tool_metadata(source="caller-supplied-source-bound-event-evidence", observed_at=max((item.published_at for item in valid), default=None),
                         analysis_cutoff=analysis_cutoff, freshness="AS_OF_CUTOFF" if valid else "UNKNOWN",
                         data_quality="PASS" if valid else "MISSING",
                         provenance="QualitativeEventEvidence source_reference + provenance",
                         errors=[] if valid else ["EVENT_EVIDENCE_MISSING"],
                         warnings=["QUALITATIVE_EVIDENCE_NOT_EXECUTION_QUOTE_AUTHORITY", "SOURCE_AND_CURRENT_RELEVANCE_NOT_INDEPENDENTLY_VERIFIED", *([f"EVENTS_AFTER_CUTOFF:{excluded}"] if excluded else [])]),
    }


@mcp.tool(title="Macro context", annotations=READ_ONLY, structured_output=True)
def macro_context(observations: list[MacroObservation], analysis_cutoff: datetime) -> dict[str, Any]:
    """Return compact cutoff-safe macro observations when supplied by a source."""
    try:
        context = compact_macro_context(tuple(observations), analysis_cutoff)
    except ValueError as error:
        context = {}
        errors = [str(error)]
    else:
        errors = [] if context else ["MACRO_CONTEXT_MISSING"]
    return {
        "status": "AVAILABLE" if context else "UNAVAILABLE",
        "series": context,
        **_tool_metadata(source="provenance-bearing-macro-observations", observed_at=analysis_cutoff if context else None,
                         analysis_cutoff=analysis_cutoff, freshness="AS_OF_CUTOFF" if context else "UNKNOWN",
                         data_quality="PASS" if context else "MISSING",
                         provenance="MacroObservation release/available timestamps and source",
                         errors=errors),
    }

@mcp.tool(title="Research packet", annotations=READ_ONLY, structured_output=True)
def research_packet(package: ResearchEvidencePackage | None = None, symbol: str | None = None,
                    analysis_cutoff: datetime | None = None) -> dict[str, Any]:
    """Retrieve evidence by symbol, or inspect a supplied validated package."""
    if package is None:
        cutoff = analysis_cutoff or datetime.now(UTC)
        if not symbol:
            return {"status": "REJECTED", "errors": ["SYMBOL_OR_PACKAGE_REQUIRED"], "execution_authority": "NONE"}
        facts = company_facts(symbol, cutoff)
        market = market_snapshot([symbol], cutoff)
        return {"status": "DATA_DEGRADED", "symbol": symbol.upper(),
                "company_facts": facts, "market": market,
                "unknowns": ["NEWS_NOT_RETRIEVED", "MACRO_NOT_RETRIEVED", "VALUATION_INPUTS_REQUIRE_VALIDATION"],
                **_tool_metadata(source="meridian-deterministic-research-packet", observed_at=None,
                                 analysis_cutoff=cutoff, freshness="SEE_COMPONENTS", data_quality="SEE_COMPONENTS",
                                 provenance="component source hashes and fact IDs", errors=[*facts.get("errors", []), *market.get("errors", [])])}
    return {"status": package.status.value, "packet": package.research_view(),
            **_tool_metadata(source="meridian-research-evidence-package",
                             observed_at=package.created_at, analysis_cutoff=package.as_of,
                             freshness=package.quality.grade.value,
                             data_quality=package.status.value,
                             provenance="ResearchEvidencePackage provenance-bearing view",
                             errors=list(package.unresolved))}


@mcp.tool(title="Quant metrics", annotations=READ_ONLY, structured_output=True)
def quant_metrics(
    symbol: str,
    bars: list[dict[str, Any]],
    analysis_cutoff: datetime,
    spy_bars: list[dict[str, Any]] | None = None,
    qqq_bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive a bounded research view; callers receive metrics, never raw rows back."""
    def parse(rows: list[dict[str, Any]]) -> list[Bar]:
        return [
            Bar(timestamp=datetime.fromisoformat(str(row["observed_at"])), open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])), low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])), volume=int(row["volume"]))
            for row in rows
        ]

    try:
        parsed, parsed_spy, parsed_qqq = parse(bars), parse(spy_bars or []), parse(qqq_bars or [])
    except (KeyError, ValueError, ArithmeticError, TypeError):
        return {"status": "REJECTED", "metrics": {}, **_tool_metadata(
            source="caller-supplied-provenance-bearing-bars", observed_at=None,
            analysis_cutoff=analysis_cutoff, freshness="UNKNOWN", data_quality="REJECTED",
            provenance="none", errors=["MALFORMED_BAR_SERIES"])}
    if analysis_cutoff.tzinfo is None or not parsed or any(item.timestamp > analysis_cutoff for item in [*parsed, *parsed_spy, *parsed_qqq]):
        return {"status": "REJECTED", "metrics": {}, **_tool_metadata(
            source="caller-supplied-provenance-bearing-bars", observed_at=None,
            analysis_cutoff=analysis_cutoff, freshness="UNKNOWN", data_quality="REJECTED",
            provenance="none", errors=["BAR_AFTER_CUTOFF_OR_EMPTY"])}
    for series in (parsed, parsed_spy, parsed_qqq):
        series.sort(key=lambda item: item.timestamp)
        if len({item.timestamp.date() for item in series}) != len(series) or any(
            not all(value.is_finite() and value > 0 for value in (item.open, item.high, item.low, item.close))
            or item.low > min(item.open, item.close) or item.high < max(item.open, item.close)
            for item in series
        ):
            return {"status": "REJECTED", "metrics": {}, "errors": ["INVALID_OR_DUPLICATE_BAR"], "execution_authority": "NONE"}
    metrics = derive_market_features(tuple(parsed), as_of=analysis_cutoff,
                                     benchmark_bars=tuple(parsed_spy), qqq_bars=tuple(parsed_qqq))
    return {"status": "AVAILABLE", "symbol": symbol.upper(),
            "metrics": {key: str(value) for key, value in metrics.items() if value is not None},
            "research_view": {"raw_series_omitted": True, "observation_count": len(parsed),
                              "latest_valid_session": parsed[-1].timestamp.isoformat(),
                              "spy_observation_count": len(parsed_spy), "qqq_observation_count": len(parsed_qqq)},
            **_tool_metadata(source="meridian-derived-market-features-v2",
                             observed_at=parsed[-1].timestamp, analysis_cutoff=analysis_cutoff,
                             freshness="HISTORICAL_UNVERIFIED", data_quality="UNVERIFIED_INPUT",
                             warnings=["CALLER_SUPPLIED_BARS_NOT_SOURCE_VERIFIED"],
                             provenance="deterministic calculation from caller-supplied bars; no source certification")}

@mcp.tool(title="Portfolio context", annotations=READ_ONLY, structured_output=True)
def portfolio_context(account: AccountSnapshot, analysis_cutoff: datetime) -> dict[str, Any]:
    total = Decimal(account.total_equity)
    errors = account_snapshot(account, analysis_cutoff)["errors"]
    return {"status": "AVAILABLE" if not errors else "DEGRADED",
            "cash": str(account.cash), "total_equity": str(account.total_equity),
            "cash_weight": str(Decimal(account.cash) / total if total else Decimal("0")),
            "positions": [{"ticker": item.ticker, "market_value": str(item.market_value),
                           "weight": str(Decimal(item.market_value) / total if total else Decimal("0"))}
                          for item in account.holdings],
            **_tool_metadata(source="authorized-sanitized-account-snapshot", observed_at=account.as_of,
                             analysis_cutoff=analysis_cutoff, freshness=account.freshness_state.value,
                             data_quality="PASS" if not errors else "DEGRADED",
                             provenance="in-memory AccountSnapshot; no account identifiers persisted",
                             errors=errors)}


@mcp.tool(title="Risk analysis", annotations=READ_ONLY, structured_output=True)
def risk_analysis(account: AccountSnapshot, analysis_cutoff: datetime) -> dict[str, Any]:
    errors = account_snapshot(account, analysis_cutoff)["errors"]
    total = Decimal(account.total_equity)
    gross = sum((Decimal(item.market_value) for item in account.holdings), Decimal("0"))
    return {"status": "REJECTED" if errors else "ACCOUNT_CONTEXT_ONLY", "gross_exposure": None if errors else str(gross / total if total else Decimal("0")),
            "warning": "A proposed deterministic target portfolio is required for order-level risk approval.",
            **_tool_metadata(source="meridian-deterministic-risk-context", observed_at=account.as_of,
                             analysis_cutoff=analysis_cutoff, freshness=account.freshness_state.value,
                             data_quality="DEGRADED", provenance="AccountSnapshot only; no target supplied",
                             errors=errors, warnings=["NO_TARGET_PORTFOLIO_NO_ORDER_RISK_APPROVAL"])}


@mcp.tool(title="Forward evidence", annotations=READ_ONLY, structured_output=True)
def forward_evidence() -> dict[str, Any]:
    payload = _service().forward_status()
    return {**payload, **_tool_metadata(source="meridian-forward-evidence-ledger",
                                         observed_at=None, analysis_cutoff=None,
                                         freshness="HISTORICAL", data_quality=str(payload.get("status")),
                                         provenance="append-only ForwardLedger",
                                         warnings=["FORWARD_EVIDENCE_NEVER_GRANTS_AUTOMATIC_PROMOTION"])}


@mcp.tool(title="Daily closure", annotations=READ_ONLY, structured_output=True)
def daily_closure(account: AccountSnapshot, quotes: list[MarketSnapshot], analysis_cutoff: datetime) -> dict[str, Any]:
    result = DailyClosureService(load_policies(policy_directory())).run(
        account, {item.ticker: item for item in quotes}, cutoff=analysis_cutoff
    )
    return {"status": result.decision.overall_status.value, "decision": result.decision.model_dump(mode="json"),
            "report": result.report, **_tool_metadata(source="meridian-daily-closure",
            observed_at=analysis_cutoff, analysis_cutoff=analysis_cutoff, freshness="AS_OF_CUTOFF",
            data_quality="PASS" if not result.decision.blocked_reasons else "BLOCKED",
            provenance=str(result.report["output_hash"]), errors=list(result.decision.blocked_reasons),
            warnings=["BROKER_SUBMISSION_DISABLED"])}


@mcp.tool(title="Audit lookup", annotations=READ_ONLY, structured_output=True)
def audit_lookup(run_id: str) -> dict[str, Any]:
    result = get_run(run_id)
    return {**result, **_tool_metadata(source="meridian-audit-store", observed_at=None,
                                        analysis_cutoff=None, freshness="HISTORICAL",
                                        data_quality="PASS" if result.get("found") else "MISSING",
                                        provenance="sanitized immutable audit summary",
                                        errors=[] if result.get("found") else ["RUN_NOT_FOUND"])}


async def health(_: Any) -> JSONResponse:
    return JSONResponse(
        {"status": "ok", "service": "meridian-alpha", "execution_capability": False}
    )


app = mcp.streamable_http_app()
app.routes.append(Route("/health", health))


def main() -> None:
    """Run the Codex-discoverable stdio server by default."""
    mcp.run(transport="stdio")


def http_main() -> None:
    """Explicit local HTTP host for supervised diagnostics only."""
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()


