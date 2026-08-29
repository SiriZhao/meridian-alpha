from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from meridian.host_account import (
    HostAccountSnapshotEnvelope,
    HostCoverageStatus,
    HostPosition,
    HostSnapshotRegistry,
    normalize_host_snapshot,
)
from meridian.schemas import AccountSyncState, FreshnessState

T = datetime(2026, 8, 30, 14, 30, tzinfo=UTC)


def envelope(**updates: Any) -> HostAccountSnapshotEnvelope:
    values: dict[str, Any] = {
        "snapshot_id": "host-fixture-1", "source_kind": "HOST", "source_name": "fixture",
        "as_of": T, "retrieved_at": T, "coverage_status": HostCoverageStatus.COMPLETE,
        "base_currency": "USD", "cash": Decimal("50000"), "total_equity": Decimal("50000"),
        "positions": (),
    }
    values.update(updates)
    return HostAccountSnapshotEnvelope(**values)


def test_complete_host_envelope_normalizes_without_private_identifier() -> None:
    snapshot = normalize_host_snapshot(envelope(), now=T)
    assert snapshot.account_alias == "host-sanitized"
    assert snapshot.provider == "host-envelope"
    assert snapshot.sync_state is AccountSyncState.SYNCED


def test_partial_and_stale_remain_non_executable_account_states() -> None:
    partial = normalize_host_snapshot(envelope(coverage_status=HostCoverageStatus.PARTIAL), now=T)
    stale = normalize_host_snapshot(envelope(as_of=T - timedelta(hours=1)), now=T, max_age_seconds=60)
    assert partial.sync_state is AccountSyncState.PARTIAL
    assert stale.freshness_state is FreshnessState.STALE


def test_unknown_security_and_currency_mismatch_fail_closed() -> None:
    with pytest.raises(ValueError, match="SECURITY_IDENTITY_UNAVAILABLE"):
        normalize_host_snapshot(envelope(positions=(HostPosition(ticker="UNKNOWN", quantity=Decimal("1"), market_value=Decimal("1")),)), now=T)
    with pytest.raises(ValueError, match="CURRENCY_MISMATCH"):
        normalize_host_snapshot(envelope(positions=(HostPosition(ticker="AAPL", quantity=Decimal("1"), market_value=Decimal("100"), currency="EUR"),)), now=T)


def test_duplicate_snapshot_id_with_changed_content_fails_closed() -> None:
    registry = HostSnapshotRegistry()
    normalize_host_snapshot(envelope(), now=T, registry=registry)
    with pytest.raises(ValueError, match="DUPLICATE_SNAPSHOT_ID_CONTENT_CONFLICT"):
        normalize_host_snapshot(envelope(cash=Decimal("49000"), total_equity=Decimal("49000")), now=T, registry=registry)