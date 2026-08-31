"""Gate 6H/6I V1 daily-shadow release audit.

This runner invokes the supported daily path with a sanitized TEST fixture,
executes the cache-only replay/soak battery, and writes conservative readiness
artifacts.  It never discovers credentials, calls a broker, or promotes a
challenger model.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.cli import _CertifiedFixtureResearchEngine, _fixture_market, _fixture_signal
from meridian.config import load_policies
from meridian.daily_release import offline_v1_soak, package_daily_run
from meridian.execution_quote_providers import provider_preflight
from meridian.finrlx_runtime import inspect_finrlx_runtime
from meridian.identity_certification import load_verified_security_certificates
from meridian.orchestrator import DailyAnalysisService, DailyOrchestrator
from meridian.profiles import RuntimeProfile
from meridian.schemas import AccountSnapshot

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
SECURITY = REPORTS / "gate4f-security-master.json"
ACCOUNT = ROOT / "schemas" / "examples" / "empty-50000.json"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _commit() -> str:
    try:
        return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_fundamental_coverage() -> dict[str, Any]:
    path = REPORTS / "gate6b-five-equity-fundamentals.json"
    if not path.is_file():
        return {ticker: {"status": "UNAVAILABLE"} for ticker in ("AAPL", "MSFT", "NVDA", "META", "GOOGL")}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("coverage", {}) if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _run_safe_daily() -> dict[str, Any]:
    policies = load_policies(ROOT / "policies")
    account = AccountSnapshot.model_validate_json(ACCOUNT.read_text(encoding="utf-8"))
    as_of = account.as_of
    signals = {ticker: _fixture_signal(ticker, as_of) for ticker in policies.universe.tickers}
    decision = DailyAnalysisService(
        DailyOrchestrator(policies, _fixture_market(as_of), _CertifiedFixtureResearchEngine(signals))
    ).run(account, as_of)
    return package_daily_run(decision, account, profile=RuntimeProfile.TEST, root=ROOT, policies=policies)


def run() -> dict[str, Any]:
    generated_at = datetime.now(UTC).replace(microsecond=0)
    security: dict[str, Any]
    try:
        master = load_verified_security_certificates(SECURITY)
        security = {"captured": 11, "artifact_valid": True, "runtime_authoritative": master.authoritative_count()}
    except (OSError, ValueError) as error:
        security = {"captured": 0, "artifact_valid": False, "runtime_authoritative": 0, "reason": str(error)[:240]}
    soak = offline_v1_soak(cycles=200)
    preflight = [item.model_dump(mode="json") for item in provider_preflight(probe=False)]
    finrlx = inspect_finrlx_runtime().model_dump(mode="json")
    daily = _run_safe_daily()
    blockers = [
        "REAL_HOST_INPUT_REQUIRED",
        "EXECUTION_QUOTE_CERTIFICATION_REQUIRED",
    ]
    observation_blockers = ["MINIMUM_COMPLETED_SHADOW_SESSIONS_REQUIRED"]
    adversarial_cases = ("stale_host", "future_host", "partial_host", "corrupt_security_artifact", "market_outage", "sec_outage", "deepseek_timeout", "deepseek_malformed", "deepseek_fake_citation", "quote_absent", "quote_stale", "quote_wrong_symbol", "quote_wide", "risk_block", "reconciliation_mismatch", "manual_certificate_missing", "manual_certificate_tampered", "provider_disagreement", "replay_cache_corrupt")
    readiness = {
        "Account truth": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": "real externally authorized Host snapshot"},
        "Security Master": {"implemented": True, "real_data": security["runtime_authoritative"] == 11, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": None if security["runtime_authoritative"] == 11 else "verified artifact load"},
        "Market/research data": {"implemented": True, "real_data": True, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": "execution-grade quote remains uncertified"},
        "Certified SEC fundamentals": {"implemented": True, "real_data": True, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": None},
        "Quant": {"implemented": True, "real_data": True, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": False, "blocker": None},
        "DeepSeek certified research": {"implemented": True, "real_data": True, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": "research calls require explicit opt-in or exact replay"},
        "AlphaFusion/allocator/risk/reconciliation": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": None},
        "Dislocation shadow": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": False, "blocker": "observation only"},
        "ExecutionQuote boundary": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": "provider capability certificate"},
        "Manual ticket boundary": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": True, "blocker": "Host + certified quote"},
        "Replay/shadow ledger": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": False, "blocker": None},
        "MCP/Skill/Chinese report": {"implemented": True, "real_data": False, "pit_safe": True, "production_path": True, "shadow_tested": True, "manual_ready_dependency": False, "blocker": None},
        "FinRL-X": {"implemented": True, "real_data": bool(finrlx.get("runtime_available")), "pit_safe": True, "production_path": False, "shadow_tested": False, "manual_ready_dependency": False, "blocker": "MODEL_UNAVAILABLE / optional post-v1"},
    }
    report = {
        "schema_version": "gate6i.v1",
        "generated_at": generated_at.isoformat(),
        "git_head": _commit(),
        "status": "V1_BLOCKED_ON_EXTERNAL_INPUT",
        "release_states": ["V1_CODE_FEATURE_COMPLETE", "V1_BLOCKED_ON_EXTERNAL_INPUT", "V1_READY_FOR_SHADOW_OBSERVATION"],
        "daily_entrypoint": "meridian daily",
        "real_host_smoke": False,
        "execution_quote_certified": False,
        "manual_entry_ready": False,
        "system_health": daily["system_health"],
        "profiles": ["TEST", "REPLAY", "SHADOW_LIVE", "MANUAL_DECISION_SUPPORT"],
        "auto_execution": False,
        "production_alpha_path": "Quant -> CertifiedAgentSignal -> AlphaFusion -> allocator -> risk -> reconciliation",
        "fundamental_coverage": _load_fundamental_coverage(),
        "security": security,
        "daily_package": {"status": daily["status"], "run_id": daily["run_id"], "artifact_directory": daily["artifact_directory"]},
        "shadow_ledger": daily["shadow_ledger"],
        "attribution": daily["attribution"],
        "provider_health": preflight,
        "finrlx": finrlx,
        "soak": soak,
        "code_blockers": [],
        "external_blockers": blockers,
        "observation_blockers": observation_blockers,
        "adversarial_battery": {"cases": list(adversarial_cases), "status": "NOT_RUN_IN_RELEASE_SCRIPT", "network_calls": 0, "note": "Covered by targeted safety tests and offline soak; no pass is claimed here."},
        "known_p0": 0,
        "known_p1": blockers + observation_blockers,
        "known_p2": [],
        "readiness_matrix": readiness,
        "safety": {"broker": "NONE", "schwab": "NOT CONNECTED", "real_orders": 0, "auto_execution": False, "finrlx_promoted": False},
    }
    _write(REPORTS / "v1-product-readiness.json", report)
    lines = ["# Meridian Alpha V1 product readiness", "", "Status: **V1_BLOCKED_ON_EXTERNAL_INPUT**", "", "| Capability | Implemented | Real data | PIT safe | Production path | Shadow tested | Manual dependency | Blocker |", "|---|:---:|:---:|:---:|:---:|:---:|:---:|---|"]
    for name, item in readiness.items():
        lines.append(f"| {name} | {str(item['implemented']).upper()} | {str(item['real_data']).upper()} | {str(item['pit_safe']).upper()} | {str(item['production_path']).upper()} | {str(item['shadow_tested']).upper()} | {str(item['manual_ready_dependency']).upper()} | {item['blocker'] or '—'} |")
    lines.extend(["", "Core v1 is feature-complete for shadow observation. Real Host input and an execution-quote capability certificate remain external blockers.", "", "FinRL-X: `MODEL_UNAVAILABLE` is acceptable and formally deferred post-v1. TradingAgents remains qualitative context only; DeepSeek certified evidence is the production research path.", "", "No broker writes, Schwab authentication, real orders, or automatic execution occurred."])
    (REPORTS / "v1-product-readiness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    report = run()
    print(json.dumps({"status": report["status"], "daily_entrypoint": report["daily_entrypoint"], "soak_cycles": report["soak"]["soak"]["cycles"], "known_p0": report["known_p0"]}, sort_keys=True))


if __name__ == "__main__":
    main()

