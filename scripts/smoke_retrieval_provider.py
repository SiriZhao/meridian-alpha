"""Opt-in one-symbol real Codex planner + structured retrieval smoke test."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from meridian.config import load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.operational_data import FreshnessPolicy
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.research_agents.preparation import ResearchPreparationService
from meridian.runtime import RuntimePaths, policy_directory


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def main() -> int:
    paths = RuntimePaths.from_environment()
    paths.ensure_directories()
    policies = load_policies(policy_directory())
    settings = policies.models.research
    if settings is None:
        print(json.dumps({"status": "BLOCKED", "error": "RESEARCH_NOT_CONFIGURED"}))
        return 2
    now = datetime.now(UTC)
    market = OperationalMarketSnapshotService.from_runtime(
        paths,
        policy=FreshnessPolicy(
            quote_max_age_seconds=policies.data.quote_max_age_seconds,
            account_max_age_seconds=policies.data.account_snapshot_max_age_seconds,
        ),
    ).build(["NVDA"], analysis_time=now, live=True)
    quote = market.research_quotes.get("NVDA")
    if quote is None:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": market.missing_symbols.get("NVDA", "MARKET_DATA_MISSING"),
                    "provider_probes": market.provider_probes,
                },
                default=str,
            )
        )
        return 2
    cutoff = market.information_cutoff
    request = DailyResearchInput(
        parent_run_id="retrieval-smoke",
        analysis_cutoff=cutoff,
        mode="LIVE",
        snapshot_reference=_hash("SMOKE_TEST_NO_ACCOUNT_PAYLOAD"),
        market_reference=market.snapshot_hash,
        policy_reference=_hash(policies.models.model_dump(mode="json")),
        provider=settings.provider,
        model=settings.model,
        observations=(
            PublicResearchObservation(
                ticker="NVDA",
                observed_at=quote.timestamp,
                price=quote.last,
                daily_return=quote.daily_return,
                reference=_hash(quote.model_dump(mode="json")),
            ),
        ),
        freshness_status="PASS",
        provider_provenance={"NVDA": json.dumps(market.provider_probes.get("NVDA", {}), default=str)},
    )
    result = ResearchPreparationService.from_runtime(paths).prepare(
        request, settings.model_copy(update={"live_enabled": True})
    )
    print(
        json.dumps(
            {
                "status": result.error_code or result.package.status.value,
                "package_status": result.package.status.value,
                "error_code": result.error_code,
                "initial_completeness": str(result.initial_completeness),
                "final_completeness": str(result.package.quality.completeness),
                "quality_score": result.package.quality.score,
                "quality_grade": result.package.quality.grade.value,
                "source_count": result.package.source_count,
                "retrieval_rounds": result.package.rounds,
                "planner_rounds": result.planner_rounds,
                "blocking_missing": list(result.package.quality.blocking_missing),
                "planner_summary": result.package.planner_summary,
                "providers": [
                    {
                        "provider": item.provider,
                        "requirement": item.requirement_key,
                        "success": bool(item.evidence),
                        "failure": item.failure.reason if item.failure else None,
                        "cache_hit": item.cache_hit,
                    }
                    for item in result.package.provider_results
                ],
                "evidence_fields": sorted({item.field for item in result.package.evidence}),
                "raw_account_persisted": False,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if result.error_code is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
