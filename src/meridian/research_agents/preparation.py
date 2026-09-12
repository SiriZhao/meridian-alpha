"""Agentic, bounded preparation loop before canonical Codex research."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import Field

from meridian.config import ResearchSettings
from meridian.daily_research import DailyResearchInput
from meridian.data.models import (
    DataCategory,
    DataStatus,
    EvidenceRecord,
    ProviderResult,
    RequirementStatus,
    ResearchDataRequirement,
    ResearchEvidencePackage,
    SourceType,
    ValidationStatus,
)
from meridian.data.providers.structured import (
    HistoricalSeriesRetrievalProvider,
    SecFundamentalRetrievalProvider,
    YahooMacroRetrievalProvider,
)
from meridian.data.retrieval_orchestrator import (
    DataQualityGate,
    EvidenceCache,
    RetrievalOrchestrator,
)
from meridian.historical import NasdaqHistoricalProvider, YahooChartHistoricalProvider
from meridian.operational_market_snapshot import ResilientHistoricalProvider
from meridian.research_agents.data_gap_planner import DataGapPlan, DataGapPlanner, GapPlanner
from meridian.runtime import RuntimePaths
from meridian.schemas import StableModel
from meridian.security_master import DEFAULT_SECURITY_MASTER


class ResearchPreparationResult(StableModel):
    request: DailyResearchInput
    package: ResearchEvidencePackage
    initial_completeness: Decimal = Field(ge=0, le=1)
    planner_rounds: int = Field(ge=0, le=4)
    error_code: str | None = None


class ResearchPreparationService:
    """Ask Codex what is missing, retrieve real evidence, and recheck up to three times."""

    def __init__(
        self,
        planner: GapPlanner,
        orchestrator: RetrievalOrchestrator,
        *,
        strategy_profile_path: Path,
        max_retrieval_rounds: int = 3,
        clock: Any = None,
    ) -> None:
        self.planner = planner
        self.orchestrator = orchestrator
        self.strategy_profile_path = strategy_profile_path
        self.max_retrieval_rounds = max_retrieval_rounds
        self.clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_runtime(cls, paths: RuntimePaths) -> ResearchPreparationService:
        root = Path(__file__).resolve().parents[3]
        profile = root / "policies" / "strategy_profile.json"
        if not profile.is_file():
            profile = Path(__file__).resolve().parents[1] / "policies" / "strategy_profile.json"
        history = ResilientHistoricalProvider(
            (
                YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=8.0),
                NasdaqHistoricalProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=8.0),
            ),
            paths.cache / "market" / "daily",
        )
        providers = (
            HistoricalSeriesRetrievalProvider(history),
            SecFundamentalRetrievalProvider(),
            YahooMacroRetrievalProvider(),
        )
        return cls(
            DataGapPlanner(),
            RetrievalOrchestrator(
                providers,
                cache=EvidenceCache(paths.cache / "research-evidence"),
                audit_root=paths.logs / "retrieval",
                max_retries=1,
            ),
            strategy_profile_path=profile,
        )

    def prepare(
        self, request: DailyResearchInput, settings: ResearchSettings
    ) -> ResearchPreparationResult:
        strategy = self._strategy_profile()
        requirements = list(self._baseline_requirements(request, strategy))
        evidence = list(self._initial_evidence(request, strategy))
        package = self._package_without_retrieval(
            request, requirements, evidence, status=DataStatus.DATA_DEGRADED
        )
        initial_completeness = package.quality.completeness
        planner_rounds = 0
        last_plan: DataGapPlan | None = None
        provider_results: list[ProviderResult] = []
        # Baseline structured requirements are deterministic and already known.
        # Retrieve them before asking Codex to plan optional gaps so a model
        # timeout cannot erase usable market history from this run.
        package = self.orchestrator.retrieve(
            requirements,
            as_of=request.analysis_cutoff,
            existing_evidence=evidence,
            rounds=0,
            planner_summary="BASELINE_DETERMINISTIC_RETRIEVAL",
        )
        provider_results.extend(package.provider_results)
        evidence = list(package.evidence)
        for round_number in range(1, self.max_retrieval_rounds + 1):
            try:
                last_plan = self.planner.analyze(self._planner_context(request, package), settings)
            except RuntimeError as error:
                code = str(error) if str(error).startswith("CODEX_") else "GPT_PLANNER_FAILED"
                failed = package.model_copy(
                    update={
                        "status": DataStatus.GPT_PLANNER_FAILED,
                        "unresolved": tuple(dict.fromkeys((*package.unresolved, code))),
                        "planner_summary": str(error),
                    }
                )
                failed = self._mark_available_requirements(failed)
                return ResearchPreparationResult(
                    request=request.model_copy(update={"evidence_package": failed.research_view()}),
                    package=failed,
                    initial_completeness=initial_completeness,
                    planner_rounds=planner_rounds,
                    error_code=code,
                )
            planner_rounds += 1
            requirements = self._merge_requirements(
                requirements, (*last_plan.missing, *last_plan.optional_missing)
            )
            before = len(evidence)
            package = self.orchestrator.retrieve(
                requirements,
                as_of=request.analysis_cutoff,
                existing_evidence=evidence,
                rounds=round_number,
                planner_summary=last_plan.reasoning_summary,
            )
            provider_results.extend(package.provider_results)
            package = package.model_copy(update={"provider_results": tuple(provider_results)})
            evidence = list(package.evidence)
            if not package.quality.blocking_missing and last_plan.sufficient:
                break
            if len(evidence) == before:
                break

        # A final planner pass is a sufficiency audit, not a fourth retrieval round.
        try:
            final_plan = self.planner.analyze(self._planner_context(request, package), settings)
            planner_rounds += 1
        except RuntimeError as error:
            code = str(error) if str(error).startswith("CODEX_") else "GPT_PLANNER_FAILED"
            failed = package.model_copy(
                update={
                    "status": DataStatus.GPT_PLANNER_FAILED,
                    "unresolved": tuple(dict.fromkeys((*package.unresolved, code))),
                    "planner_summary": str(error),
                }
            )
            failed = self._mark_available_requirements(failed)
            return ResearchPreparationResult(
                request=request.model_copy(update={"evidence_package": failed.research_view()}),
                package=failed,
                initial_completeness=initial_completeness,
                planner_rounds=planner_rounds,
                error_code=code,
            )
        all_requirements = self._merge_requirements(
            requirements, (*final_plan.missing, *final_plan.optional_missing)
        )
        quality, status = self.orchestrator.quality_gate.evaluate(
            all_requirements, package.evidence, package.conflicts, as_of=request.analysis_cutoff
        )
        unresolved = list(quality.blocking_missing)
        unresolved.extend(
            item.key
            for item in final_plan.missing
            if item.required and item.key not in package.available_keys
        )
        if unresolved and status is DataStatus.DATA_COMPLETE:
            status = DataStatus.DATA_RETRIEVAL_FAILED
        available_keys = package.available_keys
        conflict_keys = {item.requirement_key for item in package.conflicts}
        resolved_requirements = tuple(
            item.model_copy(
                update={
                    "status": RequirementStatus.CONFLICT
                    if item.key in conflict_keys
                    else RequirementStatus.RETRIEVED
                    if item.key in available_keys
                    else RequirementStatus.FAILED
                }
            )
            for item in all_requirements
        )
        final_package = package.model_copy(
            update={
                "requirements": resolved_requirements,
                "provider_results": tuple(provider_results),
                "quality": quality.model_copy(
                    update={"blocking_missing": tuple(dict.fromkeys(unresolved))}
                ),
                "status": status,
                "planner_summary": final_plan.reasoning_summary,
                "unresolved": tuple(dict.fromkeys(unresolved)),
            }
        )
        error_code = None
        if final_package.quality.blocking_missing:
            error_code = final_package.status.value
        enriched = request.model_copy(update={"evidence_package": final_package.research_view()})
        return ResearchPreparationResult(
            request=enriched,
            package=final_package,
            initial_completeness=initial_completeness,
            planner_rounds=planner_rounds,
            error_code=error_code,
        )

    def _strategy_profile(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.strategy_profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("STRATEGY_PROFILE_INVALID") from error
        if not isinstance(payload, dict) or payload.get("automatic_broker_execution") is not False:
            raise RuntimeError("STRATEGY_PROFILE_INVALID")
        return payload

    @staticmethod
    def _baseline_requirements(
        request: DailyResearchInput, strategy: dict[str, Any]
    ) -> tuple[ResearchDataRequirement, ...]:
        requirements: list[ResearchDataRequirement] = []
        for item in request.observations:
            requirements.extend(
                (
                    ResearchDataRequirement(
                        symbol=item.ticker,
                        asset_type="EQUITY_OR_ETF",
                        field="current_market_snapshot",
                        category=DataCategory.MARKET_SNAPSHOT,
                        required=True,
                        freshness_requirement="1d_research_only",
                        preferred_sources=("canonical_market_stage",),
                        reason="Blocking current research observation",
                    ),
                    ResearchDataRequirement(
                        symbol=item.ticker,
                        asset_type="EQUITY_OR_ETF",
                        field="daily_ohlcv_1y",
                        category=DataCategory.PRICE_HISTORY,
                        required=True,
                        lookback="1y",
                        frequency="1d",
                        freshness_requirement="1d",
                        preferred_sources=("yahoo", "trusted_web_outer_astra"),
                        allow_web_fallback=True,
                        reason="Blocking trend, volume, and risk history",
                    ),
                    ResearchDataRequirement(
                        symbol=item.ticker,
                        asset_type="EQUITY_OR_ETF",
                        field="latest_fundamentals",
                        category=DataCategory.FUNDAMENTALS,
                        required=False,
                        lookback="2y",
                        freshness_requirement="7d",
                        preferred_sources=("sec",),
                        reason="Optional primary-source fundamental context",
                    ),
                )
            )
        requirements.extend(
            (
                ResearchDataRequirement(
                    symbol="PORTFOLIO",
                    asset_type="PORTFOLIO",
                    field="portfolio_context",
                    category=DataCategory.PORTFOLIO_CONTEXT,
                    required=True,
                    freshness_requirement="current_run",
                    preferred_sources=("meridian_snapshot_reference",),
                    reason="Blocking portfolio state reference",
                ),
                ResearchDataRequirement(
                    symbol="MERIDIAN",
                    asset_type="POLICY",
                    field="strategy_policy",
                    category=DataCategory.INVESTMENT_HORIZON,
                    required=True,
                    freshness_requirement="configuration_version",
                    preferred_sources=("strategy_profile",),
                    reason="Blocking investment horizon and strategy constraints",
                ),
                ResearchDataRequirement(
                    symbol="SPY",
                    asset_type="ETF",
                    field="benchmark_ohlcv_1y",
                    category=DataCategory.BENCHMARK,
                    required=False,
                    lookback="1y",
                    frequency="1d",
                    preferred_sources=("yahoo", "trusted_web_outer_astra"),
                    allow_web_fallback=True,
                    reason="Optional benchmark-relative analysis",
                ),
                ResearchDataRequirement(
                    symbol="VIX",
                    asset_type="INDEX",
                    field="vix",
                    category=DataCategory.MACRO,
                    required=False,
                    freshness_requirement="1d",
                    preferred_sources=("structured_market_provider",),
                    reason="Optional volatility regime context",
                ),
            )
        )
        return tuple(requirements)

    def _initial_evidence(
        self, request: DailyResearchInput, strategy: dict[str, Any]
    ) -> tuple[EvidenceRecord, ...]:
        retrieved_at = self.clock()
        evidence = [
            EvidenceRecord(
                requirement_key=f"{item.ticker}:MARKET_SNAPSHOT:current_market_snapshot",
                field="current_market_snapshot",
                category=DataCategory.MARKET_SNAPSHOT,
                value={"price": str(item.price), "daily_return": str(item.daily_return)},
                unit="USD_AND_RATIO",
                symbol=item.ticker,
                timestamp=item.observed_at,
                as_of=request.analysis_cutoff,
                source="canonical-market-stage",
                source_type=SourceType.STRUCTURED_PROVIDER,
                retrieved_at=retrieved_at,
                provider="operational-provider-chain",
                confidence=Decimal("0.85"),
                raw_reference=item.reference,
                validation_status=ValidationStatus.PASS,
            )
            for item in request.observations
        ]
        evidence.extend(
            (
                EvidenceRecord(
                    requirement_key="PORTFOLIO:PORTFOLIO_CONTEXT:portfolio_context",
                    field="portfolio_context",
                    category=DataCategory.PORTFOLIO_CONTEXT,
                    value=request.portfolio_context
                    or {
                        "snapshot_reference": request.snapshot_reference,
                        "portfolio_values_available": False,
                        "raw_account_persisted": False,
                    },
                    unit="CURRENT_PORTFOLIO_CONTEXT",
                    symbol="PORTFOLIO",
                    timestamp=request.analysis_cutoff,
                    as_of=request.analysis_cutoff,
                    source="meridian-account-snapshot-validation",
                    source_type=SourceType.PORTFOLIO_REFERENCE,
                    retrieved_at=retrieved_at,
                    provider="meridian",
                    confidence=Decimal("1"),
                    raw_reference=request.snapshot_reference,
                    validation_status=ValidationStatus.PASS,
                ),
                EvidenceRecord(
                    requirement_key="MERIDIAN:INVESTMENT_HORIZON:strategy_policy",
                    field="strategy_policy",
                    category=DataCategory.INVESTMENT_HORIZON,
                    value=strategy,
                    unit="POLICY",
                    symbol="MERIDIAN",
                    timestamp=request.analysis_cutoff,
                    as_of=request.analysis_cutoff,
                    source=str(self.strategy_profile_path),
                    source_type=SourceType.POLICY,
                    retrieved_at=retrieved_at,
                    provider="meridian-policy",
                    confidence=Decimal("1"),
                    raw_reference=request.policy_reference,
                    validation_status=ValidationStatus.PASS,
                ),
            )
        )
        return tuple(evidence)

    def _package_without_retrieval(
        self,
        request: DailyResearchInput,
        requirements: Sequence[ResearchDataRequirement],
        evidence: Sequence[EvidenceRecord],
        *,
        status: DataStatus,
    ) -> ResearchEvidencePackage:
        quality, evaluated_status = DataQualityGate().evaluate(
            requirements, evidence, (), as_of=request.analysis_cutoff
        )
        return ResearchEvidencePackage(
            as_of=request.analysis_cutoff,
            created_at=self.clock(),
            status=evaluated_status if status is DataStatus.DATA_DEGRADED else status,
            requirements=tuple(requirements),
            evidence=tuple(evidence),
            quality=quality,
            source_count=len({(item.provider, item.source) for item in evidence}),
            unresolved=quality.blocking_missing,
        )

    @staticmethod
    def _planner_context(
        request: DailyResearchInput, package: ResearchEvidencePackage
    ) -> dict[str, Any]:
        return {
            "as_of": request.analysis_cutoff.isoformat(),
            "candidate_symbols": [item.ticker for item in request.observations],
            "available_evidence": [
                {
                    "requirement_key": item.requirement_key,
                    "symbol": item.symbol,
                    "field": item.field,
                    "category": item.category.value,
                    "timestamp": item.timestamp.isoformat(),
                    "provider": item.provider,
                    "validation_status": item.validation_status.value,
                }
                for item in package.evidence
            ],
            "current_quality": package.quality.model_dump(mode="json"),
            "unresolved": list(package.unresolved),
            "authority": "RESEARCH_PLANNING_ONLY_NO_VALUES",
        }

    @staticmethod
    def _mark_available_requirements(
        package: ResearchEvidencePackage,
    ) -> ResearchEvidencePackage:
        """Preserve honest availability diagnostics if the planner itself fails."""
        available = package.available_keys
        return package.model_copy(
            update={
                "requirements": tuple(
                    item.model_copy(
                        update={
                            "status": RequirementStatus.RETRIEVED
                            if item.key in available
                            else RequirementStatus.FAILED
                        }
                    )
                    for item in package.requirements
                )
            }
        )

    @staticmethod
    def _merge_requirements(
        current: Sequence[ResearchDataRequirement], additions: Sequence[ResearchDataRequirement]
    ) -> list[ResearchDataRequirement]:
        merged = {item.key: item for item in current}
        for item in additions:
            if item.key not in merged:
                merged[item.key] = item.model_copy(update={"status": RequirementStatus.MISSING})
        return list(merged.values())[:80]
