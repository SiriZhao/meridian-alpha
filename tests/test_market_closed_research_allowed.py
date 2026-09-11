from datetime import UTC, datetime, timedelta
from decimal import Decimal

from meridian.codex_provider import CodexProviderResult, CodexRunDiagnostics, ResearchResponse
from meridian.config import ResearchSettings
from meridian.daily_research import ResearchProviderStatus, SymbolResearch
from meridian.market_status import MarketStatus, market_status
from meridian.research_stage import CanonicalResearchStage
from tests.retrieval_helpers import research_request


class CompleteResearchProvider:
    def run(self, request, settings):
        observation = request.observations[0]
        response = ResearchResponse(
            status="OK",
            summary="Evidence supports a neutral review.",
            market_regime="NEUTRAL",
            confidence=Decimal("0.6"),
            recommended_action="HOLD",
            recommended_exposure_change="MAINTAIN",
            rationale="No forced transaction.",
            results=(
                SymbolResearch(
                    ticker=observation.ticker,
                    direction="NEUTRAL",
                    research_conviction=Decimal("0.6"),
                    thesis="Hold for review.",
                    cited_evidence_ids=(observation.reference,),
                    claim_kind="MODEL_INFERENCE",
                    data_limitations=("Market is closed.",),
                ),
            ),
        )
        return CodexProviderResult(
            response=response,
            attempts=1,
            diagnostics=CodexRunDiagnostics(
                model_requested="CLI_DEFAULT",
                reasoning_effort="medium",
                started_at=request.analysis_cutoff,
                elapsed_ms=1,
                exit_code=0,
                schema_valid=True,
                research_status="OK",
                input_packet_hash="a" * 64,
                output_hash="b" * 64,
            ),
        )


def test_market_closed_does_not_prevent_research_completion() -> None:
    saturday = datetime(2026, 9, 12, 16, tzinfo=UTC)
    assert market_status(saturday).status is MarketStatus.CLOSED
    request = research_request(cutoff=saturday)
    settings = ResearchSettings(
        provider="codex_cli", model="codex-default", timeout_seconds=30,
        max_retries=0, debate_rounds=0, max_parallel_tickers=1,
        minimum_research_coverage=Decimal("1"), live_enabled=True,
    )
    result = CanonicalResearchStage(
        provider=CompleteResearchProvider(), clock=lambda: saturday + timedelta(seconds=1)
    ).run(request, settings)
    assert result.context.status is ResearchProviderStatus.AVAILABLE
