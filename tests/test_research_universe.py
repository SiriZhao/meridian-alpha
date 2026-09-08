from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.config import ResearchBudgetPolicy, load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.research_stage import CanonicalResearchStage
from meridian.research_universe import ResearchResourceProfile, ResearchUniverseScheduler
from meridian.runtime import policy_directory
from meridian.schemas import FreshnessState, MarketSnapshot


def budget(limit: int = 500) -> ResearchBudgetPolicy:
    return ResearchBudgetPolicy(
        max_graph_tickers_per_run=limit,
        max_parallel_graphs=1,
        max_graph_age_hours=24,
        always_review_existing_holdings=True,
        candidate_selection_mode="existing_then_order",
    )


def quote(ticker: str, rank: int, observed_at: datetime) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        timestamp=observed_at,
        last=Decimal("100"),
        previous_close=Decimal("99"),
        volume=rank + 1,
        daily_return=Decimal("0.01"),
        freshness_state=FreshnessState.VERIFIED,
    )


def universe(size: int, observed_at: datetime) -> dict[str, MarketSnapshot]:
    return {
        (ticker := f"S{index:04d}"): quote(ticker, index, observed_at)
        for index in range(size)
    }


@pytest.mark.parametrize(
    ("size", "expected_count", "expected_mode"),
    [
        (5000, 500, "reduced"),
        (1000, 500, "reduced"),
        (500, 500, "full"),
        (100, 100, "full"),
    ],
)
def test_universe_sizes_respect_hard_budget_and_degrade_gracefully(
    size: int, expected_count: int, expected_mode: str
) -> None:
    now = datetime.now(UTC)
    quotes = universe(size, now)
    scheduler = ResearchUniverseScheduler(
        ResearchResourceProfile(cpu_count=16, memory_bytes=32 * 1024**3)
    )

    plan = scheduler.plan(tuple(quotes), quotes, policy=budget())

    assert plan.original_count == size
    assert plan.research_count == expected_count
    assert plan.deep_analysis_count == expected_count
    assert plan.mode == expected_mode
    assert plan.selection_basis == (
        "FULL_UNIVERSE" if expected_mode == "full" else "HIGH_LIQUIDITY"
    )
    assert len(plan.deep_analysis_universe) <= plan.policy_limit


def test_resource_capacity_can_reduce_deep_analysis_below_research_universe() -> None:
    now = datetime.now(UTC)
    quotes = universe(500, now)
    scheduler = ResearchUniverseScheduler(
        ResearchResourceProfile(cpu_count=4, memory_bytes=6 * 1024**3)
    )

    plan = scheduler.plan(tuple(quotes), quotes, policy=budget())

    assert plan.research_count == 500
    assert plan.resource_limit == 250
    assert plan.deep_analysis_count == 250
    assert plan.mode == "reduced"


def test_reduced_pool_uses_liquidity_and_preserves_required_holding_review() -> None:
    now = datetime.now(UTC)
    quotes = universe(10, now)
    scheduler = ResearchUniverseScheduler(
        ResearchResourceProfile(cpu_count=16, memory_bytes=32 * 1024**3)
    )

    plan = scheduler.plan(
        tuple(quotes),
        quotes,
        policy=budget(3),
        existing_holdings=("S0000",),
    )

    assert plan.deep_analysis_universe == ("S0000", "S0009", "S0008")
    assert plan.mode == "reduced"


def test_reduced_universe_reaches_provider_instead_of_budget_block() -> None:
    now = datetime.now(UTC)
    quotes = universe(4, now - timedelta(seconds=1))
    scheduler = ResearchUniverseScheduler(
        ResearchResourceProfile(cpu_count=16, memory_bytes=32 * 1024**3)
    )
    plan = scheduler.plan(tuple(quotes), quotes, policy=budget(3))
    observations = tuple(
        PublicResearchObservation(
            ticker=ticker,
            observed_at=quotes[ticker].timestamp,
            price=quotes[ticker].last,
            daily_return=quotes[ticker].daily_return,
            reference=(f"{index + 1:x}" * 64)[:64],
        )
        for index, ticker in enumerate(plan.deep_analysis_universe)
    )
    settings = load_policies(policy_directory()).models.research
    assert settings is not None
    settings = settings.model_copy(
        update={"live_enabled": True, "budget": budget(3), "llm_max_retries": 0}
    )
    request = DailyResearchInput(
        parent_run_id="daily-test",
        analysis_cutoff=now,
        mode="LIVE",
        snapshot_reference="paper-ledger",
        market_reference="market",
        policy_reference="policy",
        provider=settings.provider,
        model=settings.model,
        observations=observations,
        freshness_status="PASS",
        provider_provenance={item.ticker: "public-test" for item in observations},
        universe_plan=plan,
    )
    calls = 0

    def transport(*args):
        nonlocal calls
        calls += 1
        body = json.loads(args[2])
        supplied = json.loads(body["messages"][1]["content"])["observations"]
        results = [
            {
                "ticker": item["ticker"],
                "direction": "NEUTRAL",
                "research_conviction": "0.2",
                "thesis": "Price-only model inference",
                "cited_evidence_ids": [item["reference"]],
                "claim_kind": "MODEL_INFERENCE",
                "data_limitations": ["No fundamental evidence"],
            }
            for item in supplied
        ]
        response = {"choices": [{"message": {"content": json.dumps({"results": results})}}]}
        return 200, json.dumps(response).encode(), {}

    result = CanonicalResearchStage(
        transport=transport, credential=lambda: "test-secret"
    ).run(request, settings)

    assert calls == 1
    assert result.context.status == "AVAILABLE"
    assert result.error_code is None
    assert len(result.context.output.results) == 3  # type: ignore[union-attr]
