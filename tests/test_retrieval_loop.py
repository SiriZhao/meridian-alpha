import json
from decimal import Decimal
from pathlib import Path

from meridian.config import ResearchSettings
from meridian.data.models import DataCategory, RequirementStatus
from meridian.data.retrieval_orchestrator import RetrievalOrchestrator
from meridian.research_agents.data_gap_planner import DataGapPlan
from meridian.research_agents.preparation import ResearchPreparationService
from meridian.research_stage import CanonicalResearchStage
from tests.retrieval_helpers import NOW, SuccessProvider, requirement, research_request


class SequencedPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, context, settings):
        self.calls += 1
        if self.calls == 1:
            return DataGapPlan(
                sufficient=False,
                missing=(requirement(),),
                reasoning_summary="OHLCV is missing.",
                recommended_queries=("NVDA OHLCV",),
            )
        return DataGapPlan(
            sufficient=True,
            reasoning_summary="Blocking numerical evidence is present.",
        )


class RateLimitedPlanner:
    def analyze(self, context, settings):
        raise RuntimeError("CODEX_RATE_LIMITED")


def settings() -> ResearchSettings:
    return ResearchSettings(
        provider="codex_cli", model="codex-default", timeout_seconds=30,
        max_retries=0, debate_rounds=0, max_parallel_tickers=1,
        minimum_research_coverage=Decimal("1"), live_enabled=True,
    )


def test_agentic_retrieval_loop_rechecks_after_new_evidence(tmp_path: Path) -> None:
    profile = tmp_path / "strategy_profile.json"
    profile.write_text(
        json.dumps(
            {
                "strategy": "long-only",
                "investment_horizon": {"core": "months_to_years"},
                "decision_frequency": "daily",
                "automatic_broker_execution": False,
            }
        ),
        encoding="utf-8",
    )
    planner = SequencedPlanner()
    service = ResearchPreparationService(
        planner,
        RetrievalOrchestrator([SuccessProvider()], max_retries=0),
        strategy_profile_path=profile,
    )
    result = service.prepare(research_request(), settings())
    assert planner.calls >= 2
    assert result.package.rounds <= 3
    assert not result.package.quality.blocking_missing
    assert any(item.category is DataCategory.VOLATILITY for item in result.package.evidence)
    assert result.request.evidence_package is not None
    assert result.package.provider_results
    assert any(
        item.field == "daily_ohlcv_1y" and item.status is RequirementStatus.RETRIEVED
        for item in result.package.requirements
    )
    assert not any(
        item.key in result.package.available_keys and item.status is RequirementStatus.FAILED
        for item in result.package.requirements
    )


def test_research_view_omits_raw_series_and_portfolio_values(tmp_path: Path) -> None:
    profile = tmp_path / "strategy_profile.json"
    profile.write_text(
        json.dumps(
            {
                "strategy": "long-only",
                "investment_horizon": {"core": "months_to_years"},
                "automatic_broker_execution": False,
            }
        ),
        encoding="utf-8",
    )
    request = research_request().model_copy(
        update={
            "portfolio_context": {
                "cash": "100000",
                "total_equity": "100000",
                "positions": [{"ticker": "NVDA", "market_value": "50000"}],
            }
        }
    )
    result = ResearchPreparationService(
        SequencedPlanner(),
        RetrievalOrchestrator([SuccessProvider()], max_retries=0),
        strategy_profile_path=profile,
    ).prepare(request, settings())
    payload = result.request.evidence_package
    assert payload is not None
    serialized = json.dumps(payload)
    assert "100000" not in serialized
    history = next(item for item in payload["evidence"] if item["field"] == "daily_ohlcv_1y")
    assert history["value"]["raw_series_omitted"] is True
    assert "observation_count" in history["value"]


def test_rate_limited_gap_planner_preserves_actionable_codex_status(tmp_path: Path) -> None:
    profile = tmp_path / "strategy_profile.json"
    profile.write_text(
        json.dumps(
            {
                "strategy": "long-only",
                "investment_horizon": {"core": "months_to_years"},
                "automatic_broker_execution": False,
            }
        ),
        encoding="utf-8",
    )
    preparation = ResearchPreparationService(
        RateLimitedPlanner(),
        RetrievalOrchestrator([SuccessProvider()], max_retries=0),
        strategy_profile_path=profile,
    )
    prepared = preparation.prepare(research_request(), settings())
    assert prepared.error_code == "CODEX_RATE_LIMITED"
    assert any(
        item.field == "current_market_snapshot"
        and item.status is RequirementStatus.RETRIEVED
        for item in prepared.package.requirements
    )
    result = CanonicalResearchStage(
        preparation=ResearchPreparationService(
            RateLimitedPlanner(),
            RetrievalOrchestrator([SuccessProvider()], max_retries=0),
            strategy_profile_path=profile,
        ),
        clock=lambda: NOW,
    ).run(research_request(), settings())
    assert result.context.status.value == "CODEX_RATE_LIMITED"
    assert result.error_code == "CODEX_RATE_LIMITED"
