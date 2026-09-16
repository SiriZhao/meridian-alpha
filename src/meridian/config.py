"""Fail-fast typed policy configuration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskPolicy(PolicyModel):
    example_defaults: bool = True
    long_only: bool = True
    allow_leverage: bool = False
    max_position_weight: Decimal = Field(gt=0, le=1)
    max_sector_weight: Decimal = Field(gt=0, le=1)
    min_cash_weight: Decimal = Field(ge=0, lt=1)
    max_daily_turnover: Decimal = Field(gt=0, le=2)
    max_single_order_nav_percent: Decimal = Field(gt=0, le=1)
    max_number_positions: int = Field(ge=1, le=500)

    @model_validator(mode="after")
    def enforce_long_only(self) -> RiskPolicy:
        if not self.long_only or self.allow_leverage:
            raise ValueError("Meridian MVP requires long_only=true and allow_leverage=false")
        if self.max_position_weight * self.max_number_positions + self.min_cash_weight < 1:
            raise ValueError("position capacity plus cash floor cannot reach 100%")
        return self


class ExecutionPolicy(PolicyModel):
    example_defaults: bool = True
    fractional_shares: bool = False
    time_in_force: str = Field(pattern=r"^(DAY|GTC)$")
    max_chase_percent: Decimal = Field(ge=0, le=Decimal("0.20"))
    max_gap_percent: Decimal = Field(ge=0, le=Decimal("0.50"))
    minimum_order_notional: Decimal = Field(ge=0)
    account_freshness_required: bool = True
    market_quote_freshness_required: bool = True
    transaction_reserve_percent: Decimal = Field(ge=0, le=Decimal("0.10"))
    max_spread_percent: Decimal = Field(gt=0, le=Decimal("0.20"))


class UniversePolicy(PolicyModel):
    example_defaults: bool = True
    name: str = Field(pattern=r"^(sp500_sample|manual_test)$")
    tickers: tuple[str, ...] = Field(min_length=1, max_length=500)


class AllocationPolicy(PolicyModel):
    example_defaults: bool = True
    allocator_selection: str = Field(pattern=r"^(finrlx|deterministic_fallback)$")
    max_correlation_proxy_weight: Decimal = Field(gt=0, le=1)


class ResearchBudgetPolicy(PolicyModel):
    """Bounded graph-research budget; never defaults to whole-universe runs."""

    max_graph_tickers_per_run: int = Field(ge=1, le=500)
    max_parallel_graphs: int = Field(ge=1, le=32)
    max_graph_age_hours: int = Field(ge=1, le=24 * 365)
    always_review_existing_holdings: bool = True
    candidate_selection_mode: str = Field(pattern=r"^(deterministic_order|existing_then_order)$")
    minimum_quant_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"), default=Decimal("-1"))
    existing_holding_review_policy: str = Field(
        pattern=r"^(always|if_risk|never)$", default="always"
    )

    def select_candidates(
        self,
        tickers: list[str] | tuple[str, ...],
        existing_holdings: list[str] | tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        ordered = tuple(sorted({ticker.upper() for ticker in tickers}))
        if self.candidate_selection_mode == "deterministic_order":
            return ordered[: self.max_graph_tickers_per_run]
        held = tuple(sorted({ticker.upper() for ticker in existing_holdings}))
        if not self.always_review_existing_holdings:
            return ordered[: self.max_graph_tickers_per_run]
        if len(held) > self.max_graph_tickers_per_run:
            raise ValueError(
                "research budget cannot review every existing holding within max_graph_tickers_per_run"
            )
        remainder = tuple(ticker for ticker in ordered if ticker not in held)
        return (held + remainder)[: self.max_graph_tickers_per_run]


class ResearchBudget(PolicyModel):
    """Finite wall-clock budget for the GPT-native advisory pipeline."""

    total_seconds: int = Field(default=42, ge=1, le=600)
    primary_seconds: int = Field(default=16, ge=1, le=300)
    skeptic_seconds: int = Field(default=10, ge=1, le=300)
    scenario_seconds: int = Field(default=8, ge=1, le=300)
    synthesis_seconds: int = Field(default=8, ge=1, le=300)

    @model_validator(mode="after")
    def stages_fit_total_budget(self) -> ResearchBudget:
        if self.primary_seconds + self.skeptic_seconds + self.scenario_seconds + self.synthesis_seconds > self.total_seconds:
            raise ValueError("research stage budgets cannot exceed total_seconds")
        return self
class EvidencePacketPolicy(PolicyModel):
    """Conservative bounds for Meridian-owned evidence packets."""

    max_total_evidence_items: int = Field(ge=0, le=500)
    max_items_per_type: int = Field(ge=0, le=100)
    max_summary_characters_per_item: int = Field(ge=0, le=10000)


class EvidenceCompletenessPolicy(PolicyModel):
    minimum_total_items: int = Field(ge=0, le=500)
    minimum_distinct_sources: int = Field(ge=0, le=100)
    required_evidence_types: tuple[str, ...] = ()
    maximum_age_by_type: dict[str, int] = Field(default_factory=dict)
    minimum_point_in_time_quality: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_age_limits(self) -> EvidenceCompletenessPolicy:
        if any(not evidence_type.strip() for evidence_type in self.maximum_age_by_type):
            raise ValueError("maximum_age_by_type keys must not be blank")
        if any(age < 0 for age in self.maximum_age_by_type.values()):
            raise ValueError("maximum evidence ages must be non-negative")
        return self


class ModelRoutingPolicy(PolicyModel):
    """Role-specific model configuration with finite retry and timeout limits."""

    model: str = Field(min_length=1)
    reasoning_effort: str = Field(default="medium", pattern=r"^(minimal|low|medium|high|xhigh)$")
    timeout_seconds: int = Field(default=20, ge=1, le=600)
    max_attempts: int = Field(default=1, ge=1, le=2)
    retry_on_schema_error: bool = True

class ResearchSettings(PolicyModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    quick_model: str | None = Field(default=None, min_length=1)
    deep_model: str | None = Field(default=None, min_length=1)
    endpoint: str | None = Field(default=None, min_length=1)
    thinking_mode: str | None = Field(default=None, min_length=1)
    reasoning_effort: str = Field(default="medium", pattern=r"^(minimal|low|medium|high|xhigh)$")
    timeout_seconds: int = Field(ge=1, le=600)
    # ``max_retries`` is retained as a compatibility alias for existing
    # callers. New code should use the explicit LLM/graph budgets below.
    max_retries: int = Field(ge=0, le=10)
    llm_max_retries: int | None = Field(default=None, ge=0, le=10)
    graph_max_retries: int = Field(default=0, ge=0, le=3)
    max_graph_wall_time_seconds: int = Field(default=900, ge=1, le=86400)
    live_as_of_tolerance_seconds: int = Field(default=86400, ge=1, le=604800)
    debate_rounds: int = Field(ge=0, le=10)
    max_parallel_tickers: int = Field(ge=1, le=32)
    live_enabled: bool = False
    minimum_research_coverage: Decimal = Field(ge=0, le=1)
    research_engine: str = Field(default="gpt_native_v1", pattern=r"^(legacy|gpt_native_v1)$")
    native_budget: ResearchBudget = Field(default_factory=ResearchBudget)
    primary_model: str | None = Field(default=None, min_length=1)
    skeptic_model: str | None = Field(default=None, min_length=1)
    scenario_model: str | None = Field(default=None, min_length=1)
    synthesis_model: str | None = Field(default=None, min_length=1)
    models: dict[str, ModelRoutingPolicy] = Field(default_factory=dict)
    budget: ResearchBudgetPolicy = Field(
        default_factory=lambda: ResearchBudgetPolicy(
            max_graph_tickers_per_run=5,
            max_parallel_graphs=1,
            max_graph_age_hours=24,
            always_review_existing_holdings=True,
            candidate_selection_mode="existing_then_order",
        )
    )

    @model_validator(mode="after")
    def validate_model_roles(self) -> ResearchSettings:
        for name, value in (
            ("model", self.model),
            ("quick_model", self.quick_model),
            ("deep_model", self.deep_model),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"research {name} must not be blank")
        if self.provider.lower() in {"codex", "codex_cli"} and self.endpoint is not None:
            raise ValueError("Codex CLI research must not configure an HTTP endpoint")
        return self

    @property
    def llm_retry_budget(self) -> int:
        return self.max_retries if self.llm_max_retries is None else self.llm_max_retries


class ModelPolicy(PolicyModel):
    example_defaults: bool = True
    research: ResearchSettings | None = None
    tradingagents_provider: str = Field(min_length=1)
    tradingagents_model: str = Field(min_length=1)
    timeout_seconds: int = Field(ge=1, le=600)
    retry_budget: int = Field(ge=0, le=10)
    debate_rounds: int = Field(ge=0, le=10)
    allocator_selection: str = Field(pattern=r"^(finrlx|deterministic_fallback)$")

class ResearchDataPolicy(PolicyModel):
    """Freshness suitable for research facts, including prior-session closes."""

    maximum_market_age_seconds: int = Field(default=259200, ge=1, le=604800)
    require_verified_structured_market: bool = True


class ExecutionDataPolicy(PolicyModel):
    """Tighter freshness for an independently gated executable quote."""

    maximum_quote_age_seconds: int = Field(default=900, ge=1, le=86400)
    require_market_open: bool = True

class DataPolicy(PolicyModel):
    example_defaults: bool = True
    account_snapshot_max_age_seconds: int = Field(ge=1, le=604800)
    quote_max_age_seconds: int = Field(ge=1, le=86400)
    research: ResearchDataPolicy = Field(default_factory=ResearchDataPolicy)
    execution: ExecutionDataPolicy = Field(default_factory=ExecutionDataPolicy)
    nav_discrepancy_tolerance: Decimal = Field(ge=0, le=1000000000)
    historical_cache_enabled: bool = True
    evidence: EvidencePacketPolicy = Field(
        default_factory=lambda: EvidencePacketPolicy(
            max_total_evidence_items=50,
            max_items_per_type=10,
            max_summary_characters_per_item=2000,
        )
    )
    evidence_completeness: EvidenceCompletenessPolicy = Field(
        default_factory=lambda: EvidenceCompletenessPolicy(
            minimum_total_items=0,
            minimum_distinct_sources=0,
            required_evidence_types=(),
            maximum_age_by_type={},
            minimum_point_in_time_quality=Decimal("0"),
        )
    )


class ForwardHorizonPolicy(PolicyModel):
    name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    trading_sessions: int = Field(ge=1, le=2520)


class ForwardEvidencePolicy(PolicyModel):
    enabled: bool = True
    benchmark: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    minimum_mature_samples: int = Field(ge=1, le=100000)
    horizons: tuple[ForwardHorizonPolicy, ...] = Field(min_length=1, max_length=12)
    allowed_modes: tuple[str, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_horizons(self) -> ForwardEvidencePolicy:
        if len({item.name for item in self.horizons}) != len(self.horizons):
            raise ValueError("forward evidence horizon names must be unique")
        allowed = {
            "PURE_QUANT",
            "QUANT_PLUS_PROBABILITY",
            "QUANT_PLUS_LLM",
            "QUANT_PLUS_PROBABILITY_PLUS_LLM",
            "FULL_INTELLIGENCE_ADAPTIVE_EXPOSURE",
        }
        if any(mode not in allowed for mode in self.allowed_modes):
            raise ValueError("forward evidence contains an unsupported mode")
        return self


@dataclass(frozen=True)
class Policies:
    risk: RiskPolicy
    execution: ExecutionPolicy
    universe: UniversePolicy
    allocation: AllocationPolicy
    models: ModelPolicy
    data: DataPolicy


_FILES: dict[str, type[PolicyModel]] = {
    "risk": RiskPolicy,
    "execution": ExecutionPolicy,
    "universe": UniversePolicy,
    "allocation": AllocationPolicy,
    "models": ModelPolicy,
    "data": DataPolicy,
}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"malformed YAML: {path.name}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"policy must be a mapping: {path.name}")
    return raw


def load_policies(directory: Path) -> Policies:
    """Load all policies atomically; any invalid/missing file aborts startup."""
    loaded: dict[str, PolicyModel] = {}
    for name, model in _FILES.items():
        path = directory / f"{name}.yaml"
        if not path.is_file():
            raise ValueError(f"missing policy file: {path.name}")
        try:
            loaded[name] = model.model_validate(_load_yaml(path))
        except ValidationError as error:
            raise ValueError(f"invalid policy {path.name}: {error}") from error
    return Policies(**loaded)  # type: ignore[arg-type]


def load_forward_evidence_policy(directory: Path) -> ForwardEvidencePolicy:
    """Load the separately versioned forward-evidence policy.

    It is deliberately outside ``Policies`` so historical callers that only
    need a decision policy do not silently acquire a new promotion surface.
    Canonical application orchestration loads it explicitly.
    """
    path = directory / "forward_evidence.yaml"
    if not path.is_file():
        raise ValueError(f"missing policy file: {path.name}")
    try:
        return ForwardEvidencePolicy.model_validate(_load_yaml(path))
    except ValidationError as error:
        raise ValueError(f"invalid policy {path.name}: {error}") from error
