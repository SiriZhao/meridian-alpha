from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.host_account import HostAccountSnapshotEnvelope, HostCoverageStatus
from meridian.host_readiness import (
    ReadinessStatus,
    build_host_smoke_report,
    evaluate_host_readiness,
)
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState

T = datetime(2026, 8, 30, 14, 30, tzinfo=UTC)


def test_missing_host_input_is_explicitly_supervised_and_not_manual() -> None:
    report = build_host_smoke_report(None)
    assert report.status == "READY_FOR_SUPERVISED_HOST_INPUT"
    assert report.real_host_input is False
    assert report.gate_map["MANUAL_ENTRY_READY"].status is ReadinessStatus.FAIL


def test_partial_or_stale_host_cannot_self_authorize_manual_entry() -> None:
    account = AccountSnapshot(
        snapshot_id="host", account_alias="host-sanitized", provider="host-envelope", as_of=T,
        total_equity=Decimal("1000"), cash=Decimal("1000"), sync_state=AccountSyncState.PARTIAL,
        freshness_state=FreshnessState.VERIFIED,
    )
    gates = evaluate_host_readiness(account, security_ready=True, quote_ready=True, risk_ready=True)
    assert next(item for item in gates if item.gate == "ACCOUNT_READY").status is ReadinessStatus.DEGRADED
    assert next(item for item in gates if item.gate == "MANUAL_ENTRY_READY").status is ReadinessStatus.FAIL

    envelope = HostAccountSnapshotEnvelope(
        snapshot_id="future", source_kind="HOST", source_name="fixture", as_of=T + timedelta(seconds=1),
        retrieved_at=T + timedelta(seconds=1), coverage_status=HostCoverageStatus.COMPLETE,
        cash=Decimal("1000"), total_equity=Decimal("1000"),
    )
    with pytest.raises(ValueError, match="AS_OF_IN_FUTURE"):
        build_host_smoke_report(envelope, trusted_now=T, replay=True)

