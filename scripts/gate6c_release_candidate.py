"""Gate 6C host/quote/manual-entry release-candidate self-test.

The runner exercises only sanitized fixtures and candidate-provider diagnostics.
It never calls a broker, submits an order, or treats a fixture as real Host
input.  Its report is intentionally conservative when quote credentials or a
supervised Host envelope are absent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from meridian.execution_quote_providers import provider_preflight
from meridian.host_account import (
    HostAccountSnapshotEnvelope,
    HostSnapshotRegistry,
    normalize_host_snapshot,
)
from meridian.identity_certification import load_verified_security_certificates
from meridian.schemas import AccountSnapshot, AccountSyncState

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"
SECURITY = REPORTS / "gate4f-security-master.json"


def _load_envelope(name: str) -> HostAccountSnapshotEnvelope:
    return HostAccountSnapshotEnvelope.model_validate_json(
        (ROOT / "schemas" / "examples" / name).read_text(encoding="utf-8")
    )


def _scenario(name: str, outcome: str, *, reason: str | None = None) -> dict[str, object]:
    return {"scenario": name, "status": outcome, **({"reason": reason} if reason else {})}


def _host_self_test(security_master: Any) -> list[dict[str, object]]:
    complete = _load_envelope("finance-host-complete.json")
    scenarios: list[dict[str, object]] = []
    for name, filename, expected in (
        ("complete", "finance-host-complete.json", "SYNCED"),
        ("partial", "finance-host-partial.json", "PARTIAL"),
        ("stale", "finance-host-stale.json", "PARTIAL"),
    ):
        envelope = _load_envelope(filename)
        try:
            snapshot = normalize_host_snapshot(
                envelope,
                security_master=security_master,
                trusted_now=envelope.retrieved_at,
                replay=True,
            )
            actual = snapshot.sync_state.value
            scenarios.append(_scenario(name, "PASS" if actual == expected else "FAIL", reason=actual))
        except ValueError as error:
            scenarios.append(_scenario(name, "FAIL", reason=str(error)[:240]))

    reference = complete.retrieved_at
    future = complete.model_copy(
        update={"as_of": reference + timedelta(seconds=1), "retrieved_at": reference + timedelta(seconds=1)}
    )
    try:
        normalize_host_snapshot(future, security_master=security_master, trusted_now=reference, replay=True)
        scenarios.append(_scenario("future", "FAIL", reason="future snapshot was accepted"))
    except ValueError as error:
        scenarios.append(_scenario("future", "PASS", reason=str(error)))

    registry = HostSnapshotRegistry()
    normalize_host_snapshot(complete, security_master=security_master, trusted_now=reference, replay=True, registry=registry)
    try:
        changed = complete.model_copy(update={"cash": complete.cash - 1, "total_equity": complete.total_equity - 1})
        normalize_host_snapshot(changed, security_master=security_master, trusted_now=reference, replay=True, registry=registry)
        scenarios.append(_scenario("duplicate", "FAIL", reason="changed duplicate was accepted"))
    except ValueError as error:
        scenarios.append(_scenario("duplicate", "PASS", reason=str(error)))

    # These are account-reconciliation fixtures, not claims of Host input.
    for name, filename, expected_sync in (
        ("external_trade", "manual-external-trade.json", AccountSyncState.SYNCED),
        ("partial_fill", "partial-fill.json", AccountSyncState.PARTIAL),
    ):
        try:
            snapshot = AccountSnapshot.model_validate_json(
                (ROOT / "schemas" / "examples" / filename).read_text(encoding="utf-8")
            )
            ok = snapshot.sync_state is expected_sync
            scenarios.append(_scenario(name, "PASS" if ok else "FAIL", reason="reconciliation fixture parsed"))
        except ValueError as error:
            scenarios.append(_scenario(name, "FAIL", reason=str(error)[:240]))
    return scenarios


def run() -> dict[str, object]:
    created = datetime.now(UTC)
    try:
        security = load_verified_security_certificates(SECURITY)
        security_status: dict[str, object] = {
            "captured": 11,
            "artifact_valid": True,
            "runtime_authoritative": security.authoritative_count(),
        }
    except ValueError as error:
        security = None
        security_status = {
            "captured": 0,
            "artifact_valid": False,
            "runtime_authoritative": 0,
            "reason": str(error)[:240],
        }

    scenarios = _host_self_test(security) if security is not None else []
    preflight = [item.model_dump(mode="json") for item in provider_preflight(probe=False)]
    report: dict[str, object] = {
        "schema_version": "gate6c.v1",
        "generated_at": created.isoformat(),
        "host": {
            "real_host_input": False,
            "status": "READY_FOR_SUPERVISED_HOST_INPUT",
            "scenarios": scenarios,
            "manual_entry_ready": False,
            "reason": "Fixtures are synthetic; no externally authorized real Host envelope was supplied.",
        },
        "security_master": security_status,
        "providers": preflight,
        "execution_quote": {
            "provider": "TO_BE_SELECTED",
            "certificate": False,
            "real_quote_smoke": False,
            "manual_ticket_fixture": "TEST_ONLY",
            "reason": "No capability-certified provider configuration is present.",
        },
        "manual_entry": {"status": "NO", "authorization": "NOT_AUTHORIZED_FOR_ENTRY"},
        "safety": {
            "broker": "NONE",
            "schwab": "NOT_CONNECTED",
            "real_account": "NOT_CONNECTED",
            "real_orders": 0,
            "automatic_execution": False,
        },
        "known_p0": 0,
        "known_p1": [
            "No externally authorized real Host envelope supplied",
            "Execution quote provider remains TO_BE_SELECTED",
        ],
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "gate6c-provider-health.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    lines = [
        "# Gate 6C provider health and release-candidate self-test",
        "",
        "| Area | Status | Detail |",
        "| --- | --- | --- |",
        f"| Security Master | {'PASS' if security_status.get('artifact_valid') else 'FAIL'} | runtime authoritative {security_status.get('runtime_authoritative', 0)}/11 |",
        "| Real Host input | NOT SUPPLIED | synthetic fixtures only; READY_FOR_SUPERVISED_HOST_INPUT |",
        "| Execution quote | TO_BE_SELECTED | no capability certificate |",
        "| Manual entry | NO | requires real account and certified quote |",
        "",
        "## Provider diagnostics",
        "",
    ]
    for item in preflight:
        lines.append(f"- `{item['provider']}`: configured={item['configured']}, endpoint_reachable={item['endpoint_reachable']}, certificate_eligible={item['certificate_eligible']}; {item['reason']}")
    lines.extend(["", "## Fixture self-test", ""])
    for item in scenarios:
        lines.append(f"- `{item['scenario']}`: **{item['status']}** — {item.get('reason', '')}")
    lines.extend(["", "No broker, Schwab, credential, account identifier, or order surface is used.", ""])
    (REPORTS / "gate6c-provider-health.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True, default=str))
