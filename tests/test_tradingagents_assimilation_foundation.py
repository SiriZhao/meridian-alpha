from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from meridian.codex_provider import CodexRunDiagnostics, ResearchPacket
from meridian.daily_research import (
    DailyResearchInput,
    PublicResearchObservation,
    ResearchFailureStatus,
)
from meridian.data.models import DataCategory, EvidenceRecord, SourceType
from meridian.temporal import ResearchTemporalContext

T = datetime(2026, 9, 18, 16, 0, tzinfo=UTC)


def request(context=None):
    return DailyResearchInput(
        parent_run_id="run-1",
        analysis_cutoff=T,
        mode="REPLAY",
        snapshot_reference="snap",
        market_reference="market",
        policy_reference="policy",
        provider="fixture",
        model="fixture",
        observations=(
            PublicResearchObservation(
                ticker="AAPL",
                observed_at=T,
                price=Decimal("100"),
                daily_return=Decimal("0"),
                reference="a" * 64,
            ),
        ),
        freshness_status="PASS",
        temporal_context=context,
    )


def test_temporal_context_is_propagated_to_provider_packet():
    context = ResearchTemporalContext(
        run_id="run-1",
        trading_date=date(2026, 9, 18),
        as_of=T,
        information_cutoff=T,
        market_session="CLOSED",
        timezone="America/New_York",
    )
    packet = ResearchPacket.from_daily_input(request(context))
    assert packet.as_of == T


def test_future_temporal_context_is_rejected():
    with pytest.raises(ValueError, match="INFORMATION_CUTOFF_AFTER_AS_OF"):
        ResearchTemporalContext(
            run_id="run-1",
            trading_date=date(2026, 9, 18),
            as_of=T,
            information_cutoff=T.replace(hour=17),
            market_session="CLOSED",
            timezone="UTC",
        )


def test_evidence_available_at_is_the_historical_visibility_boundary():
    with pytest.raises(ValueError, match="AVAILABLE_AT_AFTER_AS_OF"):
        EvidenceRecord(
            requirement_key="AAPL:FUNDAMENTALS:revenue",
            field="revenue",
            category=DataCategory.FUNDAMENTALS,
            value=1,
            unit="USD",
            symbol="AAPL",
            timestamp=T,
            as_of=T,
            available_at=T.replace(hour=17),
            source="fixture",
            source_type=SourceType.STRUCTURED_PROVIDER,
            retrieved_at=T,
            provider="fixture",
            confidence=Decimal("1"),
            raw_reference="fixture",
        )


def test_failure_taxonomy_is_explicit_and_not_an_action():
    diagnostic = CodexRunDiagnostics(
        model_requested="fixture",
        reasoning_effort="low",
        started_at=T,
        elapsed_ms=1,
        research_status="NO_ACTION",
        error_class="CODEX_SCHEMA_ERROR",
        failure_status=ResearchFailureStatus.SCHEMA_INVALID,
        input_packet_hash="hash",
    )
    assert diagnostic.failure_status is ResearchFailureStatus.SCHEMA_INVALID
    assert diagnostic.failure_status is not ResearchFailureStatus.VALID
