from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.mcp_server import registered_tool_names, validate_market_evidence
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.runtime import RuntimePaths
from meridian.trusted_web_market import (
    TrustedSourcePolicy,
    TrustedWebMarketEvidence,
    validate_trusted_market_evidence,
)

NOW = datetime(2026, 9, 11, 20, tzinfo=UTC)


def evidence(*, domain: str = "nasdaq.com", url: str | None = None, value: str = "100",
             symbol: str = "GOOGL", currency: str | None = "USD", field: str = "research_price",
             evidence_type: str = "SCALAR_MARKET_FACT", rows: tuple[dict[str, object], ...] = (),
             source_url: str | None = None, known_at: datetime | None = None) -> TrustedWebMarketEvidence:
    return TrustedWebMarketEvidence(
        symbol=symbol, field=field, value=Decimal(value), unit="USD", currency=currency,
        source_name="fixture", source_domain=domain, source_url=source_url or url or f"https://{domain}/market/googl",
        observed_at=NOW - timedelta(minutes=1), known_at=known_at or NOW - timedelta(seconds=30),
        retrieved_at=NOW, analysis_cutoff=NOW, evidence_type=evidence_type, historical_rows=rows,
    )


def test_tier_a_is_accepted_without_a_second_source() -> None:
    result = validate_trusted_market_evidence((evidence(),))
    assert result["status"] == "ACCEPTED"
    assert result["accepted"][0]["corroboration_status"] == "SINGLE_TIER_A"
    assert result["execution_authority"] == "NONE"


def test_two_independent_tier_b_sources_are_accepted() -> None:
    first = evidence(domain="finance.yahoo.com", url="https://finance.yahoo.com/quote/GOOGL")
    second = evidence(domain="reuters.com", url="https://reuters.com/markets/GOOGL")
    result = validate_trusted_market_evidence((first, second))
    assert result["status"] == "ACCEPTED"
    assert {item["corroboration_status"] for item in result["accepted"]} == {"TWO_INDEPENDENT_SOURCES"}


def test_untrusted_duplicate_conflicting_and_single_tier_b_fail_safely() -> None:
    untrusted = evidence(domain="example.invalid")
    duplicate = evidence()
    conflict = evidence(value="101", url="https://nasdaq.com/market/googl-2")
    single_b = evidence(domain="finance.yahoo.com", url="https://finance.yahoo.com/quote/GOOGL")
    assert validate_trusted_market_evidence((untrusted,))["status"] == "REJECTED"
    assert validate_trusted_market_evidence((duplicate, duplicate))["rejected"][0]["reason"] == "DUPLICATE_SOURCE"
    assert validate_trusted_market_evidence((duplicate, conflict))["status"] == "CONFLICT"
    assert validate_trusted_market_evidence((single_b,))["status"] == "INSUFFICIENT_CORROBORATION"


@pytest.mark.parametrize("update,code", [
    ({"source_url": "http://nasdaq.com/market/googl"}, "SOURCE_URL_INVALID"),
    ({"known_at": NOW + timedelta(seconds=1)}, "EVIDENCE_AFTER_CUTOFF"),
    ({"currency": "EUR"}, "CURRENCY_MISMATCH"),
])
def test_url_future_and_currency_mismatch_are_rejected_or_conflicted(update, code) -> None:
    if code == "CURRENCY_MISMATCH":
        result = validate_trusted_market_evidence((evidence(), evidence(currency="EUR", url="https://nasdaq.com/market/googl-eur")))
        assert result["status"] == "CONFLICT" and result["conflicts"][0]["reason"] == code
    elif code == "SOURCE_URL_INVALID":
        with pytest.raises(ValueError, match=code):
            evidence(**update)
    else:
        with pytest.raises(ValueError, match=code):
            evidence(**update)


def test_historical_requires_machine_readable_table_not_narrative() -> None:
    rows = ({"observed_at": NOW.isoformat(), "open": "1", "high": "2", "low": "1", "close": "2", "volume": 3},)
    accepted = evidence(evidence_type="HISTORICAL_TABLE", rows=rows)
    assert validate_trusted_market_evidence((accepted,))["status"] == "ACCEPTED"
    with pytest.raises(ValueError, match="HISTORICAL_TABLE_ROWS_REQUIRED"):
        evidence(evidence_type="HISTORICAL_TABLE")
    with pytest.raises(ValueError, match="NARRATIVE_EVIDENCE_CANNOT_CARRY_BARS"):
        evidence(rows=rows)


def test_validation_tool_and_active_runtime_have_no_stooq() -> None:
    assert "validate_market_evidence" in registered_tool_names()
    payload = validate_market_evidence([evidence()])
    assert payload["status"] == "ACCEPTED" and payload["execution_authority"] == "NONE"
    service = OperationalMarketSnapshotService.from_runtime(RuntimePaths.from_environment())
    assert service.refresh.secondary is None
    assert "stooq" not in repr(service.refresh).lower()


def test_policy_is_configurable_for_official_ir_domain() -> None:
    policy = TrustedSourcePolicy(company_ir_domains=("investor.example.com",))
    result = validate_trusted_market_evidence((evidence(domain="investor.example.com"),), policy=policy)
    assert result["status"] == "ACCEPTED"
