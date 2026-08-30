import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.company_events import company_event_from_metadata, extract_company_event
from meridian.context import MacroVintageObservation, RegimeFeature, build_market_regime_snapshot
from meridian.sec_filing_metadata import SECFilingMetadata
from meridian.security_master import SecurityIdentityUnavailable, SecurityMaster

T = datetime(2026, 8, 30, tzinfo=UTC)
H = hashlib.sha256(b"fixture").hexdigest()


def test_sec_event_requires_exact_certified_metadata_and_has_no_sentiment() -> None:
    metadata = SECFilingMetadata(
        cik="0000320193",
        accession_number="0000320193-25-000073",
        form="10-Q",
        primary_document="aapl.htm",
        filing_date="2025-08-01",
        report_period="2025-06-28",
        acceptance_datetime=T,
        retrieved_at=T,
        source_uri="https://data.sec.gov/submissions/a.json",
        content_hash=H,
    )
    event = company_event_from_metadata("AAPL", metadata)
    extracted = extract_company_event(event)
    assert event.available_for(T)
    assert extracted.extraction == "PERIODIC_FINANCIAL_FILING_AVAILABLE"


def test_macro_vintage_and_regime_reject_future_information() -> None:
    vintage = MacroVintageObservation(
        series_id="FEDFUNDS",
        observation_date="2026-08-01",
        value=Decimal("5"),
        vintage_at=T,
        retrieved_at=T,
        source_uri="https://api.stlouisfed.org",
        revision_identity="v1",
        source_hash=H,
    )
    assert vintage.available_for(T)
    with pytest.raises(ValueError, match="after cutoff"):
        build_market_regime_snapshot(
            T,
            (
                RegimeFeature(
                    name="broad_index_return",
                    value=Decimal("0.1"),
                    available_at=T + timedelta(seconds=1),
                    source_hash=H,
                ),
            ),
        )


def test_historical_identity_is_blocked_without_authoritative_continuity() -> None:
    with pytest.raises(SecurityIdentityUnavailable, match="authoritative-provenance-required"):
        SecurityMaster().identity_for_historical_replay("AAPL", T)
