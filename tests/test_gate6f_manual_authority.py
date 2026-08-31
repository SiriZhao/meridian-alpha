import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from meridian.execution_quotes import (
    ExecutionQuote,
    ExecutionQuoteCapabilityCertificate,
    ExecutionSession,
)
from meridian.host_readiness import ReadinessStatus, evaluate_host_readiness
from meridian.manual_authority import (
    ManualReadinessStatus,
    build_manual_order_draft,
    issue_manual_readiness_certificate,
)
from meridian.profiles import ReportStatus, RuntimeProfile, report_status_for
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState

T = datetime(2026, 8, 31, 14, 30, tzinfo=UTC)
H = hashlib.sha256(b"lineage").hexdigest()


def _certificate(*, quote: bool = True, market: bool = True, research: bool = True):
    gates = {
        "ACCOUNT_READY": "PASS",
        "SECURITY_READY": "PASS",
        "MARKET_READY": "PASS" if market else "FAIL",
        "RESEARCH_READY": "PASS" if research else "FAIL",
        "QUOTE_READY": "PASS" if quote else "FAIL",
        "RISK_READY": "PASS",
        "RECONCILIATION_READY": "PASS",
    }
    return issue_manual_readiness_certificate(
        certificate_id="qcap-1",
        run_id="run-1",
        decision_as_of=T,
        issued_at=T,
        hashes={name: H for name in (
            "account_snapshot_hash", "security_master_manifest_hash", "market_state_hash",
            "research_state_hash", "risk_state_hash", "reconciliation_state_hash", "policy_hash",
        )},
        gates=gates,
        execution_quote_certificate_id="qcap-1",
    )


def _quote(certificate_id: str = "qcap-1") -> tuple[ExecutionQuote, ExecutionQuoteCapabilityCertificate]:
    capability = ExecutionQuoteCapabilityCertificate(
        provider="licensed-read-only",
        bid=True,
        ask=True,
        last=True,
        timestamp_semantics_verified=True,
        freshness_policy="30 seconds",
        session_semantics="regular",
        supports_stocks=True,
        source_uri="https://provider.example/docs",
        certified_at=T,
        execution_quote_grade=True,
        certificate_id=certificate_id,
        feed="SIP",
        plan="reviewed-plan",
        capability_hash=None,
    )
    capability = capability.model_copy(update={"capability_hash": capability.computed_capability_hash})
    quote = ExecutionQuote(
        symbol="AAPL", provider_symbol="AAPL", bid=Decimal("199"), ask=Decimal("201"), last=Decimal("200"),
        timestamp=T, session=ExecutionSession.REGULAR, currency="USD", provider=capability.provider,
        retrieved_at=T, certificate_id=certificate_id, feed="SIP", plan="reviewed-plan",
    )
    return quote, capability


def test_only_seven_pass_gates_issue_ready_certificate() -> None:
    ready = _certificate()
    assert ready.status is ManualReadinessStatus.READY
    blocked = _certificate(market=False)
    assert blocked.status is ManualReadinessStatus.BLOCKED
    assert "MARKET_READY:FAIL" in blocked.blockers


def test_legacy_market_snapshot_readiness_cannot_be_manual_ready() -> None:
    account = AccountSnapshot(
        snapshot_id="host", account_alias="sanitized", provider="host-envelope", as_of=T,
        total_equity=Decimal("1000"), cash=Decimal("1000"), sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )
    gates = evaluate_host_readiness(
        account, security_ready=True, market_ready=True, research_ready=True,
        quote_ready=True, risk_ready=True, reconciliation_ready=True,
    )
    assert next(item for item in gates if item.gate == "MANUAL_ENTRY_READY").status is ReadinessStatus.FAIL


def test_manual_draft_requires_certificate_and_exact_quote() -> None:
    quote, capability = _quote()
    with pytest.raises(ValueError, match="BLOCKED_MANUAL_READINESS"):
        build_manual_order_draft(
            readiness=_certificate(quote=False), quote=quote, capability_certificate=capability,
            side="BUY", quantity=Decimal("1"), now=T,
        )
    draft = build_manual_order_draft(
        readiness=_certificate(), quote=quote, capability_certificate=capability,
        side="BUY", quantity=Decimal("1"), now=T,
    )
    assert draft.status == "NOT_EXECUTED"
    assert draft.quote_certificate_id == "qcap-1"


def test_profile_manual_support_never_uses_decision_ready_without_certificate() -> None:
    assert report_status_for(RuntimeProfile.MANUAL_DECISION_SUPPORT, None) is ReportStatus.BLOCKED


def _rehash(capability: ExecutionQuoteCapabilityCertificate) -> ExecutionQuoteCapabilityCertificate:
    return capability.model_copy(update={"capability_hash": capability.computed_capability_hash})


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"provider": "other-provider"}, "QUOTE_PROVIDER_CERTIFICATE_MISMATCH"),
        ({"symbol_scope": ("MSFT",)}, "QUOTE_CERTIFICATE_SYMBOL_SCOPE_MISMATCH"),
        ({"valid_to": T - __import__("datetime").timedelta(seconds=1)}, "QUOTE_CERTIFICATE_EXPIRED"),
        ({"feed": "OTHER_FEED"}, "QUOTE_FEED_CERTIFICATE_MISMATCH"),
    ],
)
def test_fake_or_mismatched_capability_certificates_are_blocked(update: dict[str, object], message: str) -> None:
    quote, capability = _quote()
    mutated = _rehash(capability.model_copy(update=update))
    with pytest.raises(ValueError, match=message):
            build_manual_order_draft(
                readiness=_certificate(), quote=quote, capability_certificate=mutated,
                side="BUY", quantity=Decimal("1"), now=T,
            )


def test_invalid_capability_hash_is_blocked() -> None:
    quote, capability = _quote()
    forged = capability.model_copy(update={"capability_hash": "0" * 64})
    with pytest.raises(ValueError, match="QUOTE_CAPABILITY_HASH_INVALID"):
        build_manual_order_draft(
            readiness=_certificate(), quote=quote, capability_certificate=forged,
            side="BUY", quantity=Decimal("1"), now=T,
        )


def test_closed_and_wide_quotes_are_blocked() -> None:
    quote, capability = _quote()
    closed = quote.model_copy(update={"session": ExecutionSession.CLOSED})
    with pytest.raises(ValueError, match="QUOTE_SESSION_UNSUPPORTED"):
        build_manual_order_draft(
            readiness=_certificate(), quote=closed, capability_certificate=capability,
            side="BUY", quantity=Decimal("1"), now=T,
        )
    wide = quote.model_copy(update={"bid": Decimal("100"), "ask": Decimal("200"), "last": Decimal("150")})
    with pytest.raises(ValueError, match="QUOTE_SPREAD_EXCEEDS_POLICY"):
        build_manual_order_draft(
            readiness=_certificate(), quote=wide, capability_certificate=capability,
            side="BUY", quantity=Decimal("1"), now=T,
        )


@pytest.mark.parametrize("failed_gate", (
    "ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY",
    "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY",
))
def test_each_failed_or_degraded_gate_blocks_certificate(failed_gate: str) -> None:
    gates = {name: "PASS" for name in (
        "ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY",
        "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY",
    )}
    gates[failed_gate] = "DEGRADED"
    certificate = issue_manual_readiness_certificate(
        certificate_id="blocked", run_id="run-1", decision_as_of=T, issued_at=T,
        hashes={name: H for name in (
            "account_snapshot_hash", "security_master_manifest_hash", "market_state_hash",
            "research_state_hash", "risk_state_hash", "reconciliation_state_hash", "policy_hash",
        )}, gates=gates, execution_quote_certificate_id="qcap-1",
    )
    assert certificate.status is ManualReadinessStatus.BLOCKED
    assert any(failed_gate in blocker for blocker in certificate.blockers)


def test_host_readiness_rejects_duck_typed_ready_certificate() -> None:
    account = AccountSnapshot(
        snapshot_id="host", account_alias="sanitized", provider="host-envelope", as_of=T,
        total_equity=Decimal("1000"), cash=Decimal("1000"), sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )
    gates = evaluate_host_readiness(
        account, security_ready=True, market_ready=True, research_ready=True,
        quote_ready=True, risk_ready=True, reconciliation_ready=True,
        manual_readiness_certificate=type("FakeReady", (), {"status": "READY", "gates": {}})(),
    )
    assert next(item for item in gates if item.gate == "MANUAL_ENTRY_READY").status is ReadinessStatus.FAIL


def test_mcp_refuses_ready_status_without_persisted_certificate(monkeypatch: pytest.MonkeyPatch) -> None:
    from meridian import mcp_server

    class FakeStore:
        def get_decision_summary(self, run_id: str) -> dict[str, object]:
            return {"run": {"overall_status": "READY_FOR_MANUAL_ENTRY"}, "orders": [{"status": "DRAFT"}]}

    monkeypatch.setattr(mcp_server, "STORE", FakeStore())
    result = mcp_server.get_order_ticket("run-1")
    assert result["ticket_available"] is False
    assert "CERTIFICATE" in str(result["reason"])


def test_manual_draft_has_no_fill_side_effects() -> None:
    quote, capability = _quote()
    account = AccountSnapshot(
        snapshot_id="host", account_alias="sanitized", provider="host-envelope", as_of=T,
        total_equity=Decimal("1000"), cash=Decimal("1000"), sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )
    before = account.stable_json()
    draft = build_manual_order_draft(
        readiness=_certificate(), quote=quote, capability_certificate=capability,
        side="BUY", quantity=Decimal("1"), now=T,
    )
    assert draft.status == "NOT_EXECUTED"
    assert account.stable_json() == before
