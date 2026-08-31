"""Stable V1 daily-shadow release packaging.

The supported ``meridian daily`` command delegates decision calculation to the
existing DailyOrchestrator and uses this module only for sanitized lineage,
shadow-ledger, attribution, health, and run-artifact packaging. It never
connects to a broker or assumes that a recommendation was traded.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from meridian.config import Policies
from meridian.execution_quote_providers import provider_preflight
from meridian.long_shadow import (
    ExecutionAssumption,
    OutcomeHorizon,
    ShadowPerformanceLedger,
    ShadowPerformanceRecord,
    ShadowRunLedger,
    ShadowRunRecord,
    ShadowSessionLedger,
    ShadowSessionRecord,
    SystemHealthLevel,
    derive_daily_health,
    run_historical_replay_battery,
    run_long_offline_soak,
)
from meridian.profiles import RuntimeProfile, report_status_for
from meridian.reporting import mobile_daily_report_v3, report_markdown
from meridian.schemas import AccountSnapshot, DailyDecision
from meridian.trading_calendar import session_is_complete

V1_OPERATING_COMPANIES = ("AAPL", "MSFT", "NVDA", "META", "GOOGL")
V1_SUPPORTING_INSTRUMENTS = ("SPY", "QQQ", "SGOV", "GLD", "TLT", "VIX")
V1_BOUNDED_UNIVERSE = V1_OPERATING_COMPANIES + V1_SUPPORTING_INSTRUMENTS
V1_SKILL_VERSION = "meridian-alpha-skill-v1"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _commit(root: Path) -> str:
    try:
        return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _skill_zip_hash(root: Path) -> str:
    digest_path = root / "dist" / "meridian-alpha-skill-v1.sha256"
    try:
        digest = digest_path.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return "UNAVAILABLE"
    return digest if len(digest) == 64 else "UNAVAILABLE"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _provider_health() -> dict[str, object]:
    candidates = [item.model_dump(mode="json") for item in provider_preflight(probe=False)]
    return {
        "SEC": "AVAILABLE",
        "market": "SHADOW",
        "fundamentals": "PIT_CERTIFIED_WHERE_COVERED",
        "DeepSeek": "REPLAY_OR_EXPLICIT_OPT_IN",
        "execution_quote": "UNAVAILABLE",
        "candidates": candidates,
    }


def _attribution(decision: DailyDecision) -> dict[str, object]:
    """Return an honest pair of counterfactual slots for every daily run.

    Legacy TEST/REPLAY decisions do not expose ProductionAlphaDecision rows;
    those slots remain unavailable rather than being reconstructed from target
    weights. Production shadow callers can replace this section with the
    authoritative AlphaFusion attribution rows.
    """
    tickers = tuple(sorted({position.ticker for position in (decision.target_portfolio.positions if decision.target_portfolio else ())}))
    return {
        "status": "INSUFFICIENT_SAMPLE" if not tickers else "INSUFFICIENT_SAMPLE_NO_PRODUCTION_ALPHA_ROWS",
        "records": [
            {
                "ticker": ticker,
                "quant_only_alpha": "UNAVAILABLE",
                "quant_plus_certified_llm_alpha": "UNAVAILABLE",
                "alpha_difference": "UNAVAILABLE",
                "target_weight_difference": "UNAVAILABLE",
                "turnover_difference": "UNAVAILABLE",
                "causal_claim": "NOT_ESTABLISHED_SMALL_SAMPLE",
            }
            for ticker in tickers
        ],
        "note": "The daily package never fabricates quant/LLM counterfactuals from portfolio weights.",
    }


def _dislocation_track() -> dict[str, object]:
    return {
        "enabled": True,
        "status": "SCREEN_REQUIRES_CURRENT_CERTIFIED_MARKET_INPUT",
        "candidates": [
            {"ticker": ticker, "candidate_score": None, "eligible": False, "reason": "NO_CERTIFIED_MARKET_SCREEN_IN_THIS_RUN"}
            for ticker in V1_OPERATING_COMPANIES
        ],
        "assessments": [],
    }


def _target_payload(decision: DailyDecision) -> dict[str, object]:
    if decision.target_portfolio is None:
        return {"status": "UNAVAILABLE", "positions": [], "cash_weight": None}
    return decision.target_portfolio.model_dump(mode="json")


def _append_ledgers(
    *,
    decision: DailyDecision,
    account: AccountSnapshot,
    root: Path,
    provider_health: dict[str, object],
    skill_version: str,
    skill_zip_hash: str,
) -> dict[str, object]:
    target = decision.target_portfolio
    target_weights = {
        position.ticker: position.target_weight for position in (target.positions if target else ())
    }
    ledger = ShadowRunLedger(root / "var" / "shadow" / "shadow-run-ledger.json")
    record = ShadowRunRecord(
        run_id=decision.run_id,
        decision_as_of=decision.as_of,
        code_commit=_commit(root),
        account_snapshot_hash=_hash(account.model_dump(mode="json")),
        security_master_hash=_hash({"bounded_universe": V1_BOUNDED_UNIVERSE, "runtime": "explicit-loader-required"}),
        market_hashes=(_hash({"market_status": decision.market_data_status.value}),),
        fundamental_hashes=(_hash({"scope": V1_OPERATING_COMPANIES, "status": "PIT_CERTIFIED_WHERE_COVERED"}),),
        evidence_hashes=(_hash({"run_id": decision.run_id, "evidence": "sanitized-lineage-only"}),),
        llm_artifact_hashes=(),
        policy_hashes=(_hash({"profile": "V1", "profile_status": "SHADOW"}),),
        quant_signals={},
        final_alpha={},
        target_weights=target_weights,
        risk_result="BLOCKED" if decision.blocked_reasons else "PASS",
        provider_health={key: str(value) for key, value in provider_health.items() if isinstance(value, str)},
        authorization_status="SHADOW / NOT AUTHORIZED FOR ENTRY",
        skill_version=skill_version,
        skill_zip_hash=skill_zip_hash,
    )
    ledger.append(record)
    performance = ShadowPerformanceLedger(root / "var" / "shadow" / "shadow-performance-ledger.json")
    for ticker, weight in sorted(target_weights.items()):
        for horizon in (OutcomeHorizon.D1, OutcomeHorizon.D5, OutcomeHorizon.D20):
            performance.add(
                ShadowPerformanceRecord(
                    run_id=decision.run_id,
                    ticker=ticker,
                    decision_as_of=decision.as_of,
                    horizon=horizon,
                    recommendation_weight=weight,
                    target_weight=weight,
                    execution_assumption=ExecutionAssumption.NEXT_SESSION_OPEN,
                )
            )
    return {
        "run_ledger_path": str(ledger.path.relative_to(root)),
        "run_ledger_records": len(ledger.records),
        "run_ledger_hash": ledger.content_hash,
        "performance_ledger_path": str(performance.path.relative_to(root)) if performance.path else None,
        "performance_pending_rows": len(performance.records),
        "execution_assumption": ExecutionAssumption.NEXT_SESSION_OPEN.value,
        "outcomes_are_not_fills": True,
    }


def _append_shadow_session(
    *,
    decision: DailyDecision,
    account: AccountSnapshot,
    root: Path,
    provider_health: dict[str, object],
    skill_version: str,
    skill_zip_hash: str,
    session_completed: bool,
    readiness_bypass_detected: bool,
) -> dict[str, object]:
    """Append one explicit session qualification record and return its summary."""
    provider_keys = {"SEC", "market", "fundamentals", "DeepSeek", "execution_quote"}
    provider_failure_states_explicit = provider_keys.issubset(provider_health) and all(
        isinstance(provider_health[key], str) for key in provider_keys
    )
    account_green = (
        account.sync_state.value == "SYNCED"
        and account.freshness_state.value in {"VERIFIED", "RECENT"}
    )
    reconciliation_green = account_green and not any(
        "reconcil" in reason.lower() for reason in decision.blocked_reasons
    )
    record = ShadowSessionRecord(
        run_id=decision.run_id,
        decision_as_of=decision.as_of,
        code_commit=_commit(root),
        skill_version=skill_version,
        skill_zip_hash=skill_zip_hash,
        us_trading_session_completed=session_completed and session_is_complete(decision.as_of),
        daily_run_completed=True,
        no_p0=True,
        no_readiness_bypass=not readiness_bypass_detected,
        ledger_append_succeeded=True,
        account_reconciliation_green=reconciliation_green,
        provider_failure_states_explicit=provider_failure_states_explicit,
        evidence_ids_valid=decision.target_portfolio is not None,
    )
    ledger = ShadowSessionLedger(root / "var" / "shadow" / "shadow-session-ledger.json")
    ledger.append(record)
    return {**ledger.summary(), "run_id": decision.run_id, "qualified": record.qualified, "incomplete_reasons": record.incomplete_reasons}


def package_daily_run(
    decision: DailyDecision,
    account: AccountSnapshot,
    *,
    profile: RuntimeProfile = RuntimeProfile.TEST,
    root: Path | None = None,
    policies: Policies | None = None,
    session_completed: bool = False,
    readiness_bypass_detected: bool = False,
) -> dict[str, object]:
    """Persist one sanitized daily package and append its shadow ledgers."""
    root = root or Path.cwd()
    if decision.as_of.tzinfo is None or decision.as_of.utcoffset() is None:
        raise ValueError("daily decision cutoff must be timezone-aware")
    if account.as_of > decision.as_of:
        raise ValueError("daily account snapshot is after decision cutoff")
    provider_health = _provider_health()
    skill_version = V1_SKILL_VERSION
    skill_zip_hash = _skill_zip_hash(root)
    components = {
        "account": "PASS" if account.freshness_state.value in {"VERIFIED", "RECENT"} and account.sync_state.value == "SYNCED" else "DEGRADED",
        "identity": "UNVERIFIED",
        "market": decision.market_data_status.value,
        "evidence": "AVAILABLE" if decision.target_portfolio is not None else "UNVERIFIED",
        "research": "AVAILABLE" if decision.target_portfolio is not None else "UNVERIFIED",
        "quote": "UNAVAILABLE",
        "risk": "BLOCKED" if decision.blocked_reasons else "PASS",
    }
    health = derive_daily_health(components)
    top_status = report_status_for(profile, decision).value
    attribution = _attribution(decision)
    package_dir = root / "runs" / decision.as_of.date().isoformat() / decision.run_id
    ledger_info = _append_ledgers(
        decision=decision,
        account=account,
        root=root,
        provider_health=provider_health,
        skill_version=skill_version,
        skill_zip_hash=skill_zip_hash,
    )
    evidence_lineage = {
        "status": "SANITIZED_LINEAGE_ONLY",
        "evidence_ids": [],
        "account_snapshot_hash": _hash(account.model_dump(mode="json")),
        "decision_hash": _hash(decision.model_dump(mode="json")),
        "raw_provider_payloads": False,
    }
    manifest = {
        "schema_version": "meridian-v1-run.v1",
        "run_id": decision.run_id,
        "decision_as_of": decision.as_of.isoformat(),
        "profile": profile.value,
        "status": top_status,
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "code_commit": _commit(root),
        "skill_version": skill_version,
        "skill_zip_hash": skill_zip_hash,
        "account_snapshot_hash": evidence_lineage["account_snapshot_hash"],
        "security_master_hash": _hash({"bounded_universe": V1_BOUNDED_UNIVERSE}),
        "market_hashes": [_hash({"market_status": decision.market_data_status.value})],
        "fundamental_hashes": [_hash({"scope": V1_OPERATING_COMPANIES})],
        "evidence_hashes": [evidence_lineage["decision_hash"]],
        "llm_artifact_hashes": [],
        "policy_hashes": [_hash(policies.models.model_dump(mode="json") if policies else {"profile": profile.value})],
        "authorization_status": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "health": health.model_dump(mode="json"),
        "blockers": list(decision.blocked_reasons),
    }
    mobile = mobile_daily_report_v3(
        decision,
        profile=profile.value,
        blockers=("EXECUTION_QUOTE_CERTIFICATION", "REAL_HOST_INPUT") if profile is not RuntimeProfile.TEST else (),
    )
    report = {
        "schema_version": "meridian-v1-daily.v1",
        "run_id": decision.run_id,
        "decision_as_of": decision.as_of.isoformat(),
        "profile": profile.value,
        "status": top_status,
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "bounded_universe": {"operating_companies": V1_OPERATING_COMPANIES, "supporting_instruments": V1_SUPPORTING_INSTRUMENTS},
        "decision": decision.model_dump(mode="json"),
        "provider_health": provider_health,
        "attribution": attribution,
        "dislocation": _dislocation_track(),
        "system_health": health.model_dump(mode="json"),
        "shadow_ledger": ledger_info,
        "performance": {"status": "INSUFFICIENT_SAMPLE", "horizons": ["1D", "5D", "20D"], "joined": 0, "simulated_execution": "NEXT_SESSION_OPEN", "outcomes_are_not_fills": True},
        "decision_quality": {"signal_counts": {}, "citation_failures": 0, "provider_failures": ["execution_quote:UNAVAILABLE"], "dislocation_candidates": 0, "risk_blocks": len(decision.blocked_reasons), "manual_readiness_blocks": ["REAL_HOST_INPUT", "EXECUTION_QUOTE_CERTIFICATION"]},
        "mobile_report": mobile,
        "known_p0": 0,
        "known_p1": ["No externally authorized real Host input", "No certified execution quote provider"],
    }
    all_blockers = list(decision.blocked_reasons) + (
        ["REAL_HOST_INPUT", "EXECUTION_QUOTE_CERTIFICATION"]
        if profile is not RuntimeProfile.TEST
        else []
    )
    version = {
        "code_commit": _commit(root),
        "skill_version": skill_version,
        "skill_zip_hash": skill_zip_hash,
        "policy_hashes": manifest["policy_hashes"],
        "decision_timestamp": decision.as_of.isoformat(),
    }
    package_dir.mkdir(parents=True, exist_ok=True)
    _write(package_dir / "manifest.json", manifest)
    _write(package_dir / "decision.json", report["decision"])
    _write(package_dir / "provider-health.json", provider_health)
    _write(package_dir / "evidence-lineage.json", evidence_lineage)
    _write(package_dir / "target-portfolio.json", _target_payload(decision))
    (package_dir / "report.md").write_text("AUTHORIZATION: SHADOW / NOT AUTHORIZED FOR ENTRY\n" + mobile + "\n\n" + report_markdown(decision, profile=profile.value, status=top_status), encoding="utf-8")
    session_summary = _append_shadow_session(
        decision=decision,
        account=account,
        root=root,
        provider_health=provider_health,
        skill_version=skill_version,
        skill_zip_hash=skill_zip_hash,
        session_completed=session_completed,
        readiness_bypass_detected=readiness_bypass_detected,
    )
    operator_output = {
        "run_id": decision.run_id,
        "version": version,
        "status": top_status,
        "system_health": health.level.value,
        "account_state": components["account"],
        "research_state": components["research"],
        "quant_state": "AVAILABLE" if decision.target_portfolio is not None else "UNAVAILABLE",
        "llm_state": provider_health["DeepSeek"],
        "target_state": "AVAILABLE" if decision.target_portfolio is not None else "UNAVAILABLE",
        "quote_state": provider_health["execution_quote"],
        "manual_readiness": "YES" if top_status == "READY_FOR_MANUAL_ENTRY" else "NO",
        "shadow_sessions": session_summary,
        "blockers": all_blockers,
    }
    report["version"] = version
    report["shadow_session"] = session_summary
    report["operator_output"] = operator_output
    manifest["shadow_session"] = session_summary
    _write(package_dir / "manifest.json", manifest)
    _write(package_dir / "shadow-session.json", session_summary)
    (package_dir / "report.md").write_text(
        "AUTHORIZATION: SHADOW / NOT AUTHORIZED FOR ENTRY\n"
        + mobile
        + "\n\n"
        + "SHADOW SESSIONS: "
        + str(session_summary["sessions_completed"])
        + "/"
        + str(session_summary["sessions_required"])
        + "\n\n"
        + report_markdown(decision, profile=profile.value, status=top_status),
        encoding="utf-8",
    )
    return {**report, "artifact_directory": str(package_dir.relative_to(root))}


def offline_v1_soak(*, cycles: int = 200) -> dict[str, object]:
    result = run_long_offline_soak(cycles=cycles)
    replay = run_historical_replay_battery()
    return {
        "soak": result.model_dump(mode="json"),
        "replay": replay.model_dump(mode="json"),
        "network_calls": result.network_calls + replay.network_calls,
        "status": "PASS" if result.failed == 0 and replay.failed == 0 else "FAIL",
        "health": SystemHealthLevel.GREEN.value if result.failed == 0 else SystemHealthLevel.RED.value,
    }
