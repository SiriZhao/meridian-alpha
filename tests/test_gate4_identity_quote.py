from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from meridian.execution_quotes import (
    ExecutionQuote,
    ExecutionQuoteCapabilityCertificate,
    ExecutionQuoteStatus,
    ExecutionQuoteValidator,
    ExecutionSession,
    ManualLimitPricePolicy,
    create_manual_order_draft,
)
from meridian.identity_certification import (
    IdentityCertificationRequest,
    IdentitySourceKind,
    SecurityMasterPromotionService,
    authoritative_count,
    load_certified_security_master,
)
from meridian.schemas import Side
from meridian.security_master import (
    DEFAULT_SECURITY_MASTER,
    SecurityCertificationStatus,
    SecurityMaster,
)

T = datetime(2026, 8, 30, 14, 30, tzinfo=UTC)
H = "a" * 64


def identity_request(**updates: object) -> IdentityCertificationRequest:
    values: dict[str, Any] = {
        "canonical_symbol": "AAPL",
        "legal_name": "Apple Inc.",
        "asset_type": "EQUITY",
        "source_kind": IdentitySourceKind.SEC,
        "source_name": "SEC company submissions",
        "source_uri": "https://data.sec.gov/submissions/CIK0000320193.json",
        "source_hash": H,
        "retrieved_at": T,
        "certified_at": T,
        "effective_from": datetime(1980, 12, 12, tzinfo=UTC),
        "exchange": "NASDAQ",
        "currency": "USD",
        "cik": "0000320193",
    }
    values.update(updates)
    return IdentityCertificationRequest(**values)


def test_identity_promotion_requires_primary_source_and_interval() -> None:
    master = SecurityMaster()
    result = SecurityMasterPromotionService().promote_into(master, identity_request())
    assert result.status is SecurityCertificationStatus.AUTHORITATIVE_VERIFIED
    assert authoritative_count(master) == 1
    assert master.identity_for_historical_replay("AAPL", T).canonical_symbol == "AAPL"

    rejected = SecurityMasterPromotionService().promote(
        DEFAULT_SECURITY_MASTER.resolve("AAPL"),
        identity_request(source_uri="https://example.invalid/aapl.json"),
    )
    assert rejected.status is SecurityCertificationStatus.UNVERIFIED
    assert "IDENTITY_PRIMARY_SOURCE_UNVERIFIED" in rejected.blockers


def test_captured_identity_report_is_explicitly_loadable_and_historical_bounds_hold() -> None:
    path = __import__("pathlib").Path(__file__).parents[1] / "reports" / "gate4f-security-master.json"
    master = load_certified_security_master(path)
    assert master.authoritative_count() == 11
    with pytest.raises(ValueError, match="historical-identity-unknown"):
        master.identity_for_historical_replay("AAPL", datetime(2020, 1, 1, tzinfo=UTC))


def test_quote_validator_enforces_certificate_identity_freshness_and_spread() -> None:
    certificate = ExecutionQuoteCapabilityCertificate(
        provider="licensed-read-only",
        bid=True,
        ask=True,
        last=True,
        timestamp_semantics_verified=True,
        freshness_policy="30 seconds",
        session_semantics="explicit regular/pre/after-hours",
        supports_stocks=True,
        supports_etfs=True,
        source_uri="https://provider.example/docs",
        certified_at=T,
        execution_quote_grade=True,
    )
    raw = {
        "symbol": "AAPL",
        "provider_symbol": "AAPL",
        "bid": "199.90",
        "ask": "200.10",
        "last": "200.00",
        "timestamp": T,
        "session": ExecutionSession.REGULAR,
        "currency": "USD",
        "provider": "licensed-read-only",
        "retrieved_at": T,
        "certificate_id": "cert-1",
    }
    validator = ExecutionQuoteValidator(DEFAULT_SECURITY_MASTER)
    valid = validator.validate(raw, symbol="AAPL", now=T, certificate=certificate)
    assert valid.valid and valid.quote is not None
    assert ManualLimitPricePolicy.calculate(valid.quote, Side.BUY) == Decimal("200.10")
    stale = validator.validate(raw | {"timestamp": T - timedelta(minutes=1)}, symbol="AAPL", now=T, certificate=certificate)
    assert stale.status is ExecutionQuoteStatus.STALE
    wide = validator.validate(raw | {"bid": "100", "ask": "200", "last": "150"}, symbol="AAPL", now=T, certificate=certificate)
    assert wide.status is ExecutionQuoteStatus.WIDE_SPREAD
    wrong = validator.validate(raw | {"symbol": "MSFT"}, symbol="AAPL", now=T, certificate=certificate)
    assert wrong.status is ExecutionQuoteStatus.WRONG_TICKER
    with pytest.raises(ValueError, match="bid"):
        ExecutionQuote.model_validate(raw | {"bid": "201", "ask": "200"})
    with pytest.raises(ValueError, match="MANUAL_ENTRY_BLOCKED"):
        create_manual_order_draft(
            valid.quote,
            side=Side.BUY,
            quantity=Decimal("1"),
            readiness={"ACCOUNT_READY": "PASS", "SECURITY_READY": "PASS", "QUOTE_READY": "FAIL", "RISK_READY": "PASS", "RECONCILIATION_READY": "PASS"},
        )
