"""Explicit host readiness gates and review-safe host smoke reports."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.manual_authority import ManualReadinessCertificate, ManualReadinessStatus
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState, StableModel
from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityMaster


class ReadinessStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    DEGRADED = "DEGRADED"


class ReadinessGateResult(StableModel):
    gate: str = Field(min_length=1, max_length=64)
    status: ReadinessStatus
    reason: str = Field(min_length=1, max_length=512)


class HostReadinessReport(StableModel):
    schema_version: str = Field(default="1", pattern=r"^1$")
    status: str
    real_host_input: bool
    snapshot_id: str | None = None
    source_name: str | None = None
    as_of: datetime | None = None
    retrieved_at: datetime | None = None
    coverage: str | None = None
    currency: str | None = None
    position_count: int = 0
    warnings: tuple[str, ...] = ()
    provenance_digest: str | None = None
    gates: tuple[ReadinessGateResult, ...]

    @property
    def gate_map(self) -> dict[str, ReadinessGateResult]:
        return {gate.gate: gate for gate in self.gates}


_GATES = (
    "ACCOUNT_READY",
    "SECURITY_READY",
    "MARKET_READY",
    "RESEARCH_READY",
    "QUOTE_READY",
    "RISK_READY",
    "RECONCILIATION_READY",
    "MANUAL_ENTRY_READY",
)


def _bool_gate(name: str, value: bool, reason: str) -> ReadinessGateResult:
    return ReadinessGateResult(gate=name, status=ReadinessStatus.PASS if value else ReadinessStatus.FAIL, reason=reason)


def evaluate_host_readiness(
    snapshot: AccountSnapshot | None,
    *,
    security_ready: bool = False,
    market_ready: bool = False,
    research_ready: bool = False,
    quote_ready: bool = False,
    risk_ready: bool = False,
    reconciliation_ready: bool | None = None,
    manual_readiness_certificate: object | None = None,
) -> tuple[ReadinessGateResult, ...]:
    """Evaluate all gates without changing or persisting account state."""
    if snapshot is None:
        account = ReadinessGateResult(gate="ACCOUNT_READY", status=ReadinessStatus.FAIL, reason="No sanitized Host snapshot supplied")
    elif snapshot.freshness_state in {FreshnessState.STALE, FreshnessState.UNKNOWN}:
        account = ReadinessGateResult(gate="ACCOUNT_READY", status=ReadinessStatus.FAIL, reason="Host snapshot is stale or unknown")
    elif snapshot.sync_state is AccountSyncState.PARTIAL:
        account = ReadinessGateResult(gate="ACCOUNT_READY", status=ReadinessStatus.DEGRADED, reason="Host snapshot coverage is partial")
    elif snapshot.sync_state is AccountSyncState.SYNCED:
        account = ReadinessGateResult(gate="ACCOUNT_READY", status=ReadinessStatus.PASS, reason="Fresh synchronized sanitized Host snapshot")
    else:
        account = ReadinessGateResult(gate="ACCOUNT_READY", status=ReadinessStatus.FAIL, reason="Host account sync is unavailable")
    gates = [
        account,
        _bool_gate("SECURITY_READY", security_ready, "Authoritative Security Master certification is required"),
        _bool_gate("MARKET_READY", market_ready, "Current market research data is required"),
        _bool_gate("RESEARCH_READY", research_ready, "Certified research is required for the selected profile"),
        _bool_gate("QUOTE_READY", quote_ready, "Certified execution quote is required"),
        _bool_gate("RISK_READY", risk_ready, "Deterministic risk checks have not passed"),
    ]
    recon_value = reconciliation_ready if reconciliation_ready is not None else account.status is ReadinessStatus.PASS
    gates.append(_bool_gate("RECONCILIATION_READY", recon_value, "Current account truth has not been reconciled"))
    required = {item.gate: item.status for item in gates}
    certificate_ready = (
        isinstance(manual_readiness_certificate, ManualReadinessCertificate)
        and manual_readiness_certificate.status is ManualReadinessStatus.READY
        and all(manual_readiness_certificate.gates.values())
    )
    manual = (
        all(
            required.get(name) is ReadinessStatus.PASS
            for name in (
                "ACCOUNT_READY",
                "SECURITY_READY",
                "MARKET_READY",
                "RESEARCH_READY",
                "QUOTE_READY",
                "RISK_READY",
                "RECONCILIATION_READY",
            )
        )
        and certificate_ready
    )
    gates.append(_bool_gate("MANUAL_ENTRY_READY", manual, "All seven readiness gates must pass and a READY ManualReadinessCertificate is required"))
    return tuple(gates)


def host_provenance_summary(envelope: HostAccountSnapshotEnvelope) -> dict[str, Any]:
    """Return only safe host lineage; position quantities and values are omitted."""
    return {
        "source_name": envelope.source_name,
        "source_kind": envelope.source_kind,
        "snapshot_id": envelope.snapshot_id,
        "as_of": envelope.as_of.isoformat(),
        "retrieved_at": envelope.retrieved_at.isoformat(),
        "coverage": envelope.coverage_status.value,
        "currency": envelope.base_currency,
        "position_count": len(envelope.positions),
        "warnings": list(envelope.warnings),
        "provenance_digest": envelope.provenance_digest,
    }


def build_host_smoke_report(
    envelope: HostAccountSnapshotEnvelope | None,
    *,
    security_master: SecurityMaster = DEFAULT_SECURITY_MASTER,
    externally_authorized: bool = False,
    trusted_now: datetime | None = None,
    replay: bool = False,
    security_ready: bool = False,
    market_ready: bool = False,
    research_ready: bool = False,
    quote_ready: bool = False,
    risk_ready: bool = False,
    reconciliation_ready: bool | None = None,
    manual_readiness_certificate: object | None = None,
) -> HostReadinessReport:
    if envelope is None:
        gates = evaluate_host_readiness(None)
        return HostReadinessReport(
            status="READY_FOR_SUPERVISED_HOST_INPUT",
            real_host_input=False,
            warnings=("No externally authorized sanitized Host input was supplied.",),
            gates=gates,
        )
    snapshot = normalize_host_snapshot(
        envelope,
        security_master=security_master,
        trusted_now=trusted_now,
        replay=replay,
    )
    gates = evaluate_host_readiness(
        snapshot,
        security_ready=security_ready,
        market_ready=market_ready,
        research_ready=research_ready,
        quote_ready=quote_ready,
        risk_ready=risk_ready,
        reconciliation_ready=reconciliation_ready,
        manual_readiness_certificate=manual_readiness_certificate,
    )
    manual_pass = any(item.gate == "MANUAL_ENTRY_READY" and item.status is ReadinessStatus.PASS for item in gates)
    status = "READY_FOR_MANUAL_ENTRY" if externally_authorized and manual_pass else "READY_FOR_SUPERVISED_HOST_INPUT"
    real_host_input = bool(externally_authorized)
    return HostReadinessReport(
        status=status,
        real_host_input=real_host_input,
        snapshot_id=envelope.snapshot_id,
        source_name=envelope.source_name,
        as_of=envelope.as_of,
        retrieved_at=envelope.retrieved_at,
        coverage=envelope.coverage_status.value,
        currency=envelope.base_currency,
        position_count=len(envelope.positions),
        warnings=envelope.warnings,
        provenance_digest=envelope.provenance_digest,
        gates=gates,
    )


def write_host_smoke_report(report: HostReadinessReport, json_path: Path, markdown_path: Path) -> None:
    """Write the review artifacts; values remain sanitized by construction."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Gate 4F Host smoke",
        "",
        f"Status: **{report.status}**",
        f"Real externally authorized Host input: **{report.real_host_input}**",
        "",
        "| Gate | Status | Reason |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {gate.gate} | {gate.status.value} | {gate.reason} |" for gate in report.gates)
    lines.extend(["", "No account numbers, credentials, tokens, or raw connector payloads are included."])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# A concise alias for integrations that use the gate's shorter name.
evaluate_readiness = evaluate_host_readiness
