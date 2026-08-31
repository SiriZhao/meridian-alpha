"""Gate 6G supervised Host and execution-quote convergence runner.

This runner is deliberately conservative: it consumes only an explicitly
supplied sanitized Host envelope, performs bounded read-only provider
preflight, and never turns a candidate provider into an execution capability.
Synthetic fixtures are reported as TEST_FIXTURE and can never earn a real
manual-entry status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.execution_quote_providers import provider_preflight
from meridian.execution_quotes import (
    ExecutionQuote,
    ExecutionQuoteCapabilityCertificate,
    ExecutionSession,
)
from meridian.host_account import (
    HostAccountSnapshotEnvelope,
    HostSnapshotRegistry,
    normalize_host_snapshot,
)
from meridian.host_readiness import host_provenance_summary
from meridian.identity_certification import load_verified_security_certificates
from meridian.manual_authority import build_manual_order_draft, issue_manual_readiness_certificate
from meridian.schemas import AccountSnapshot, AccountSyncState, Side

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports"
SECURITY = REPORTS / "gate4f-security-master.json"
SYMBOLS = ("AAPL", "NVDA", "SPY")


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _commit() -> str:
    try:
        return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _fixture_envelope(name: str) -> HostAccountSnapshotEnvelope:
    path = ROOT / "schemas" / "examples" / name
    return HostAccountSnapshotEnvelope.model_validate_json(path.read_text(encoding="utf-8"))


def _scenario(name: str, status: str, reason: str = "") -> dict[str, str]:
    result = {"scenario": name, "status": status}
    if reason:
        result["reason"] = reason[:240]
    return result


def _host_fixture_self_tests(security: Any) -> list[dict[str, str]]:
    complete = _fixture_envelope("finance-host-complete.json")
    scenarios: list[dict[str, str]] = []
    for name, expected, filename in (
        ("complete", AccountSyncState.SYNCED.value, "finance-host-complete.json"),
        ("partial", AccountSyncState.PARTIAL.value, "finance-host-partial.json"),
        ("stale", AccountSyncState.PARTIAL.value, "finance-host-stale.json"),
    ):
        envelope = _fixture_envelope(filename)
        try:
            snapshot = normalize_host_snapshot(envelope, security_master=security, trusted_now=envelope.retrieved_at, replay=True)
            actual = snapshot.sync_state.value
            scenarios.append(_scenario(name, "PASS" if actual == expected else "FAIL", actual))
        except ValueError as error:
            scenarios.append(_scenario(name, "FAIL", str(error)))

    reference = complete.retrieved_at
    future_data = complete.model_dump(mode="json")
    future_data.pop("provenance_digest", None)
    future_data.update({"as_of": (reference + timedelta(seconds=1)).isoformat(), "retrieved_at": (reference + timedelta(seconds=1)).isoformat()})
    future = HostAccountSnapshotEnvelope.model_validate(future_data)
    try:
        normalize_host_snapshot(future, security_master=security, trusted_now=reference, replay=True)
        scenarios.append(_scenario("future", "FAIL", "future Host snapshot was accepted"))
    except ValueError as error:
        scenarios.append(_scenario("future", "PASS", str(error)))

    registry = HostSnapshotRegistry()
    first = registry.register(complete)
    second = registry.register(complete.model_copy())
    scenarios.append(_scenario("duplicate_identical", "PASS" if (first, second) == ("REGISTERED", "DUPLICATE_IDEMPOTENT") else "FAIL", f"{first},{second}"))
    try:
        registry.register(complete.model_copy(update={"cash": complete.cash - 1, "total_equity": complete.total_equity - 1}))
        scenarios.append(_scenario("duplicate_conflict", "FAIL", "changed duplicate was accepted"))
    except ValueError as error:
        scenarios.append(_scenario("duplicate_conflict", "PASS", str(error)))

    for name, filename, expected in (("external_trade", "manual-external-trade.json", AccountSyncState.SYNCED.value), ("partial_fill", "partial-fill.json", AccountSyncState.PARTIAL.value)):
        try:
            snapshot = AccountSnapshot.model_validate_json((ROOT / "schemas" / "examples" / filename).read_text(encoding="utf-8"))
            scenarios.append(_scenario(name, "PASS" if snapshot.sync_state.value == expected else "FAIL", "sanitized reconciliation fixture"))
        except (OSError, ValueError) as error:
            scenarios.append(_scenario(name, "FAIL", str(error)))
    return scenarios


def _load_explicit_host(path: Path, security: Any, externally_authorized: bool) -> tuple[dict[str, Any], HostAccountSnapshotEnvelope | None, AccountSnapshot | None]:
    if not path.is_file():
        return {"present": False, "status": "READY_FOR_SUPERVISED_HOST_INPUT", "reason": "supplied Host path does not exist"}, None, None
    try:
        envelope = HostAccountSnapshotEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
        snapshot = normalize_host_snapshot(envelope, security_master=security)
        # An operator must explicitly attest that this is externally authorized;
        # a path alone never converts a fixture into real Host truth.
        is_real = externally_authorized and "TEMPLATE_ONLY" not in " ".join(envelope.warnings)
        account_gate_pass = snapshot.sync_state is AccountSyncState.SYNCED and snapshot.freshness_state.value in {"VERIFIED", "RECENT"}
        smoke_status = "REAL_HOST_INPUT_VALID" if is_real and account_gate_pass else "BLOCKED_REAL_HOST_INPUT" if is_real else "SUPPLIED_NOT_ATTESTED"
        return {"present": is_real, "status": smoke_status, "account_gate_pass": account_gate_pass, "provenance": host_provenance_summary(envelope), "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else "EXTERNAL_PATH_REDACTED"}, envelope, snapshot
    except (OSError, ValueError) as error:
        return {"present": False, "status": "BLOCKED_REAL_HOST_INPUT", "reason": f"HOST_SMOKE_REJECTED:{str(error)[:240]}"}, None, None


def _fixture_manual_e2e(now: datetime) -> dict[str, Any]:
    cert = ExecutionQuoteCapabilityCertificate(
        provider="fixture-read-only", certificate_id="fixture-capability-v1", feed="FIXTURE", plan="FIXTURE",
        bid=True, ask=True, last=True, timestamp_semantics_verified=True,
        freshness_policy="30 seconds", session_semantics="REGULAR",
        supports_stocks=True, supports_etfs=True, source_uri="https://example.invalid/fixture-docs",
        certified_at=now, execution_quote_grade=True,
    )
    cert = cert.model_copy(update={"capability_hash": cert.computed_capability_hash})
    quote = ExecutionQuote(
        symbol="AAPL", provider_symbol="AAPL", bid=Decimal("199.90"), ask=Decimal("200.10"), last=Decimal("200"),
        timestamp=now, retrieved_at=now, available_at=now, session=ExecutionSession.REGULAR,
        currency="USD", provider=cert.provider, feed=cert.feed, plan=cert.plan, certificate_id=cert.certificate_id,
    )
    digest = _sha("fixture-lineage")
    readiness = issue_manual_readiness_certificate(
        certificate_id="fixture-readiness-v1", run_id="gate6g-fixture", decision_as_of=now, issued_at=now,
        execution_quote_certificate_id=cert.certificate_id,
        hashes={name: digest for name in ("account_snapshot_hash", "security_master_manifest_hash", "market_state_hash", "research_state_hash", "risk_state_hash", "reconciliation_state_hash", "policy_hash")},
        gates={name: "PASS" for name in ("ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY", "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY")},
    )
    draft = build_manual_order_draft(readiness=readiness, quote=quote, capability_certificate=cert, side=Side.BUY, quantity=Decimal("1"), now=now)
    return {"status": "TEST_FIXTURE", "manual_entry_ready": False, "draft_status": draft.status, "not_executed": draft.status == "NOT_EXECUTED", "quote_provider": draft.quote_provider}


def run(*, host_path: Path | None = None, externally_authorized: bool = False, probe: bool = False) -> dict[str, Any]:
    created = _now()
    try:
        security = load_verified_security_certificates(SECURITY)
        security_info = {"captured": 11, "artifact_valid": True, "runtime_authoritative": security.authoritative_count()}
    except ValueError as error:
        security = None
        security_info = {"captured": 0, "artifact_valid": False, "runtime_authoritative": 0, "reason": str(error)[:240]}

    host_info: dict[str, Any]
    envelope: HostAccountSnapshotEnvelope | None = None
    snapshot: AccountSnapshot | None = None
    if host_path is None:
        host_info = {"present": False, "status": "READY_FOR_SUPERVISED_HOST_INPUT", "reason": "No explicitly supplied externally authorized sanitized Host envelope."}
    elif security is None:
        host_info = {"present": False, "status": "BLOCKED_REAL_HOST_INPUT", "reason": "Security Master artifact is invalid."}
    else:
        host_info, envelope, snapshot = _load_explicit_host(host_path, security, externally_authorized)

    fixture_scenarios = _host_fixture_self_tests(security) if security is not None else []
    preflight = [item.model_dump(mode="json") for item in provider_preflight(probe=probe, symbols=SYMBOLS)]
    configured = [item for item in preflight if item["configured"]]
    quote_certified = any(item["certificate_eligible"] for item in preflight)
    quote_info = {
        "providers": preflight,
        "configured_provider_count": len(configured),
        "live_probe_requested": probe,
        "live_probe_performed": bool(probe and configured),
        "certificate_issued": False,
        "status": "EXECUTION_QUOTE_CERTIFIED" if quote_certified else "BLOCKED_EXECUTION_QUOTE_CERTIFICATION",
        "reason": "No candidate provider has proven timestamp/session/freshness/licensing semantics; execution_quote_grade remains false.",
    }
    fixture_e2e = _fixture_manual_e2e(created)
    host_real = bool(host_info.get("present"))
    host_gate_pass = host_real and host_info.get("status") == "REAL_HOST_INPUT_VALID"
    manual_status = "READY_FOR_MANUAL_ENTRY" if host_gate_pass and quote_certified else "BLOCKED_REAL_HOST_INPUT" if not host_gate_pass else "BLOCKED_EXECUTION_QUOTE_CERTIFICATION"
    manual = {
        "status": manual_status,
        "manual_readiness_certificate": "NOT_ISSUED",
        "manual_entry_ready": False,
        "required_gates": ["ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY", "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY"],
        "fixture_e2e": fixture_e2e,
        "blockers": ([] if host_gate_pass else ["BLOCKED_REAL_HOST_INPUT"]) + ([] if quote_certified else ["BLOCKED_EXECUTION_QUOTE_CERTIFICATION"]),
    }
    report = {
        "schema_version": "gate6g.v1",
        "generated_at": created.isoformat(),
        "git_head": _commit(),
        "host": {"real_input_present": host_real, "smoke": host_info, "fixture_scenarios": fixture_scenarios, "real_smoke_complete": False},
        "security_master": security_info,
        "quote": quote_info,
        "manual_rc": manual,
        "safety": {"broker": "NONE", "schwab": "NOT CONNECTED", "broker_account_read": False, "real_orders": 0, "automatic_execution": False, "finrlx_promotion": False},
        "known_p0": 0,
        "known_p1": manual["blockers"],
    }
    _json(REPORTS / "gate6g-host-smoke.json", report["host"])
    _json(REPORTS / "gate6g-quote-preflight.json", quote_info)
    _json(REPORTS / "gate6g-manual-rc.json", manual)
    _write_markdown(report)
    return report


def _write_markdown(report: dict[str, Any]) -> None:
    host = report["host"]
    quote = report["quote"]
    manual = report["manual_rc"]
    host_lines = ["# Gate 6G Host smoke", "", f"Status: **{host['smoke'].get('status', 'READY_FOR_SUPERVISED_HOST_INPUT')}**", f"Real Host input present: **{host['real_input_present']}**", "", "Synthetic fixture scenarios are TEST_ONLY and do not establish external authorization.", ""]
    for row in host.get("fixture_scenarios", []):
        host_lines.append(f"- `{row['scenario']}`: **{row['status']}** — {row.get('reason', '')}")
    quote_lines = ["# Gate 6G quote preflight", "", f"Status: **{quote['status']}**", "", "| Provider | Configured | Reachable | Quote | Certificate eligible | Blockers |", "| --- | :---: | :---: | :---: | :---: | --- |"]
    for item in quote["providers"]:
        quote_lines.append(f"| {item['provider']} | {str(item['configured']).upper()} | {str(item['endpoint_reachable']).upper()} | {str(item['quote_returned']).upper()} | {str(item['certificate_eligible']).upper()} | {', '.join(item.get('blocker_codes', []))} |")
    quote_lines.extend(["", quote["reason"], ""])
    manual_lines = ["# Gate 6G manual decision-support RC", "", f"Status: **{manual['status']}**", f"Manual entry ready: **{manual['manual_entry_ready']}**", "", "| Gate | Result |", "| --- | --- |"]
    for gate in manual["required_gates"]:
        manual_lines.append(f"| {gate} | BLOCKED until real Host and certified ExecutionQuote |")
    manual_lines.extend(["", f"Fixture E2E: **{manual['fixture_e2e']['status']}**, draft={manual['fixture_e2e']['draft_status']}, not_executed={manual['fixture_e2e']['not_executed']}", "", "No broker account read, authentication, writes, or orders occurred.", ""])
    (REPORTS / "gate6g-host-smoke.md").write_text("\n".join(host_lines), encoding="utf-8")
    (REPORTS / "gate6g-quote-preflight.md").write_text("\n".join(quote_lines), encoding="utf-8")
    (REPORTS / "gate6g-manual-rc.md").write_text("\n".join(manual_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 6G supervised Host and read-only quote convergence")
    parser.add_argument("--host-envelope", type=Path, help="Explicit sanitized Host envelope; never discovers browser/credential state")
    parser.add_argument("--externally-authorized", action="store_true", help="Attest that the supplied envelope is externally authorized")
    parser.add_argument("--probe", action="store_true", help="Perform bounded read-only provider probes only when local configuration exists")
    args = parser.parse_args()
    if args.externally_authorized and args.host_envelope is None:
        parser.error("--externally-authorized requires --host-envelope")
    report = run(host_path=args.host_envelope, externally_authorized=args.externally_authorized, probe=args.probe)
    print(json.dumps({"status": report["manual_rc"]["status"], "real_host_input": report["host"]["real_input_present"], "quote_certified": report["quote"]["certificate_issued"], "known_p0": report["known_p0"]}, sort_keys=True))


if __name__ == "__main__":
    main()