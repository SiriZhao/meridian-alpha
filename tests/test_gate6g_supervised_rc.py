from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.execution_quotes import (
    ExecutionQuoteCapabilityCertificate,
    ExecutionQuoteStatus,
    ExecutionQuoteValidator,
    ExecutionSession,
)
from meridian.host_account import (
    HostAccountSnapshotEnvelope,
    HostSnapshotRegistry,
    normalize_host_snapshot,
)
from meridian.identity_certification import load_verified_security_certificates
from meridian.manual_authority import ManualReadinessStatus, issue_manual_readiness_certificate

ROOT = Path(__file__).parents[1]
T = datetime(2026, 8, 30, 14, 30, tzinfo=UTC)
H = "a" * 64


def _envelope(**updates: object) -> HostAccountSnapshotEnvelope:
    values: dict[str, object] = {
        "snapshot_id": "gate6g-test",
        "source_kind": "HOST_AUTHORIZED_SOURCE",
        "source_name": "sanitized-test-host",
        "as_of": T,
        "retrieved_at": T,
        "coverage_status": "COMPLETE",
        "base_currency": "USD",
        "cash": "1000",
        "total_equity": "1000",
        "positions": [],
    }
    values.update(updates)
    return HostAccountSnapshotEnvelope.model_validate(values)


def _capability(*, supports_indices: bool = False, certificate_id: str = "cert-6g") -> ExecutionQuoteCapabilityCertificate:
    cert = ExecutionQuoteCapabilityCertificate(
        provider="certified-read-only",
        certificate_id=certificate_id,
        feed="REVIEWED_FEED",
        plan="REVIEWED_PLAN",
        bid=True,
        ask=True,
        last=True,
        timestamp_semantics_verified=True,
        freshness_policy="30 seconds",
        session_semantics="regular",
        supports_stocks=True,
        supports_etfs=True,
        supports_indices=supports_indices,
        source_uri="https://provider.example/docs",
        certified_at=T,
        execution_quote_grade=True,
    )
    return cert.model_copy(update={"capability_hash": cert.computed_capability_hash})


def _raw_quote(**updates: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "symbol": "AAPL",
        "provider_symbol": "AAPL",
        "bid": "199.90",
        "ask": "200.10",
        "last": "200",
        "timestamp": T,
        "session": ExecutionSession.REGULAR,
        "currency": "USD",
        "provider": "certified-read-only",
        "retrieved_at": T,
        "available_at": T,
        "certificate_id": "cert-6g",
        "feed": "REVIEWED_FEED",
        "plan": "REVIEWED_PLAN",
    }
    raw.update(updates)
    return raw


def test_host_nested_sensitive_keys_and_digest_conflict_fail_closed() -> None:
    with pytest.raises(ValueError, match="HOST_SENSITIVE_FIELD_REJECTED"):
        HostAccountSnapshotEnvelope.model_validate({**_envelope().model_dump(), "warnings": ({"nested": {"refresh_token": "redacted"}},)})
    envelope = _envelope()
    assert envelope.provenance_digest == envelope.expected_provenance_digest
    forged = envelope.model_copy(update={"provenance_digest": "0" * 64})
    with pytest.raises(ValueError, match="HOST_PROVENANCE_DIGEST_MISMATCH"):
        normalize_host_snapshot(forged, trusted_now=T, replay=True)
    registry = HostSnapshotRegistry()
    assert registry.register(envelope) == "REGISTERED"
    assert registry.register(envelope.model_copy()) == "DUPLICATE_IDEMPOTENT"
    with pytest.raises(ValueError, match="DUPLICATE_SNAPSHOT_ID_CONTENT_CONFLICT"):
        registry.register(envelope.model_copy(update={"cash": Decimal("999")}))


def test_host_future_fields_rejected_by_system_clock_in_replay() -> None:
    security = load_verified_security_certificates(ROOT / "reports" / "gate4f-security-master.json")
    future = _envelope(as_of=T + timedelta(seconds=1), retrieved_at=T + timedelta(seconds=1))
    with pytest.raises(ValueError, match="AS_OF_IN_FUTURE"):
        normalize_host_snapshot(future, security_master=security, trusted_now=T, replay=True)
    future_retrieved = _envelope(retrieved_at=T + timedelta(seconds=1))
    with pytest.raises(ValueError, match="RETRIEVED_AT_IN_FUTURE"):
        normalize_host_snapshot(future_retrieved, security_master=security, trusted_now=T, replay=True)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("bid", ExecutionQuoteStatus.MISSING_BID),
        ("ask", ExecutionQuoteStatus.MISSING_ASK),
        ("currency", ExecutionQuoteStatus.WRONG_CURRENCY),
        ("symbol", ExecutionQuoteStatus.WRONG_TICKER),
    ],
)
def test_quote_instance_identity_and_missing_fields_fail_closed(field: str, expected: ExecutionQuoteStatus) -> None:
    cert = _capability()
    value: object = None if field in {"bid", "ask"} else ("MSFT" if field == "symbol" else "EUR")
    result = ExecutionQuoteValidator(load_verified_security_certificates(ROOT / "reports" / "gate4f-security-master.json")).validate(_raw_quote(**{field: value}), symbol="AAPL", now=T, certificate=cert)
    assert result.status is expected


def test_quote_vix_requires_separate_index_capability() -> None:
    cert = _capability()
    raw = _raw_quote(symbol="VIX", provider_symbol="VIX")
    result = ExecutionQuoteValidator(load_verified_security_certificates(ROOT / "reports" / "gate4f-security-master.json")).validate(raw, symbol="VIX", now=T, certificate=cert)
    assert result.status is ExecutionQuoteStatus.UNSUPPORTED_ASSET_CLASS


def test_quote_temporal_and_spread_failures_are_typed() -> None:
    cert = _capability()
    validator = ExecutionQuoteValidator(load_verified_security_certificates(ROOT / "reports" / "gate4f-security-master.json"), max_age_seconds=30)
    assert validator.validate(_raw_quote(timestamp=T - timedelta(minutes=1), available_at=T - timedelta(minutes=1)), symbol="AAPL", now=T, certificate=cert).status is ExecutionQuoteStatus.STALE
    assert validator.validate(_raw_quote(timestamp=T + timedelta(seconds=1), available_at=T + timedelta(seconds=1), retrieved_at=T + timedelta(seconds=2)), symbol="AAPL", now=T, certificate=cert).status is ExecutionQuoteStatus.FUTURE
    assert validator.validate(_raw_quote(bid="100", ask="200", last="150"), symbol="AAPL", now=T, certificate=cert).status is ExecutionQuoteStatus.WIDE_SPREAD


def test_readiness_certificate_requires_all_seven_and_fixture_is_not_real_ready() -> None:
    gates = {name: "PASS" for name in ("ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY", "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY")}
    cert = issue_manual_readiness_certificate(certificate_id="readiness-6g", run_id="run-6g", decision_as_of=T, issued_at=T, hashes={name: H for name in ("account_snapshot_hash", "security_master_manifest_hash", "market_state_hash", "research_state_hash", "risk_state_hash", "reconciliation_state_hash", "policy_hash")}, gates=gates, execution_quote_certificate_id="cert-6g")
    assert cert.status is ManualReadinessStatus.READY
    gates["QUOTE_READY"] = "FAIL"
    assert issue_manual_readiness_certificate(certificate_id="blocked", run_id="run-6g", decision_as_of=T, issued_at=T, hashes={name: H for name in ("account_snapshot_hash", "security_master_manifest_hash", "market_state_hash", "research_state_hash", "risk_state_hash", "reconciliation_state_hash", "policy_hash")}, gates=gates, execution_quote_certificate_id="cert-6g").status is ManualReadinessStatus.BLOCKED


def test_gate6g_runner_reports_missing_real_gates_without_secrets() -> None:
    from scripts.gate6g_supervised_rc import run

    report = run(probe=False)
    assert report["host"]["real_input_present"] is False
    assert report["manual_rc"]["status"] == "BLOCKED_REAL_HOST_INPUT"
    assert report["manual_rc"]["manual_entry_ready"] is False
    assert report["manual_rc"]["fixture_e2e"]["draft_status"] == "NOT_EXECUTED"
    assert report["safety"]["real_orders"] == 0