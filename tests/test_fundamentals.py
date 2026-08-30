from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.fundamentals import CanonicalMetric, CertifiedFundamentalFact, build_snapshot
from meridian.schemas import EvidencePointInTimeStatus

T = datetime(2026, 8, 30, tzinfo=UTC)


def fact(metric, value, accession="0000320193-26-000001", accepted=T, unit="USD"):
    return CertifiedFundamentalFact(
        fact_id=f"{metric}-{accession}",
        ticker="AAPL",
        cik="0000320193",
        accession_number=accession,
        form="10-Q",
        taxonomy="us-gaap",
        concept=metric,
        canonical_metric=CanonicalMetric[metric],
        value=Decimal(value),
        unit=unit,
        period_start=T - timedelta(days=90),
        period_end=T - timedelta(days=1),
        accepted_at=accepted,
        available_at=accepted,
        retrieved_at=T,
        source_uri="https://sec.example",
        source_hash="a" * 64,
        provider="sec-edgar-accession-certified",
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )


def test_fcf_has_lineage_and_later_restatement_cannot_leak():
    old = (fact("OPERATING_CASH_FLOW", "100"), fact("CAPEX", "20"), fact("NET_INCOME", "10"))
    later = fact("NET_INCOME", "999", "0000320193-26-000002", T + timedelta(days=1))
    snap = build_snapshot("AAPL", old + (later,), T)
    assert snap.derived[0].value == Decimal("80") and snap.derived[0].input_fact_ids
    assert all(item.value != Decimal("999") for item in snap.facts)


def test_non_certified_or_invalid_duration_rejected():
    with pytest.raises(ValueError):
        CertifiedFundamentalFact.model_validate({**fact("REVENUE", "1").model_dump(), "available_at": T - timedelta(seconds=1)})
