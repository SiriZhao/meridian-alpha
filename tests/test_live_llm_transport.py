"""Legacy DeepSeek transport is retained only as a fail-closed compatibility type."""

from datetime import UTC, datetime

from meridian.config import load_policies
from meridian.research import (
    DeepSeekGroundedResearchNormalizer,
    GraphResearchSummary,
    GroundedResearchStatus,
    PointInTimeStatus,
    ResearchEvidencePacket,
    ResearchStatus,
)
from meridian.runtime import policy_directory
from meridian.schemas import EvidenceItem

AS_OF = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def test_legacy_deepseek_runtime_is_disabled_without_network() -> None:
    settings = load_policies(policy_directory()).models.research
    assert settings is not None
    calls = []

    def forbidden(*args):
        calls.append(args)
        raise AssertionError("legacy DeepSeek transport must never be called")

    summary = GraphResearchSummary(
        ticker="AAPL",
        as_of=AS_OF,
        status=ResearchStatus.GRAPH_SUMMARY_ONLY,
        provider="fixture",
        model="none",
        framework_version="1",
        started_at=AS_OF,
        completed_at=AS_OF,
        point_in_time_status=PointInTimeStatus.LIVE_RESEARCH_OK,
    )
    item = EvidenceItem(
        ticker="AAPL",
        provider="fixture",
        source="fixture",
        observed_at=AS_OF,
        available_at=AS_OF,
        evidence_type="fixture",
        point_in_time_status="CERTIFIED_HISTORICAL_PIT",
        summary="fixture",
    )
    packet = ResearchEvidencePacket(
        packet_id="fixture",
        ticker="AAPL",
        as_of=AS_OF,
        items=(item,),
        point_in_time_status="CERTIFIED_HISTORICAL_PIT",
    )
    result = DeepSeekGroundedResearchNormalizer(
        settings.model_copy(update={"live_enabled": True}),
        http_post=forbidden,
        clock=lambda: AS_OF,
    ).normalize(summary, packet, AS_OF)
    assert result.status is GroundedResearchStatus.UNAVAILABLE
    assert result.error_code == "LEGACY_DEEPSEEK_RUNTIME_DISABLED"
    assert result.signal is None
    assert calls == []
