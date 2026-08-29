"""Portfolio allocation adapters with a deterministic, safe fallback."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from meridian.config import AllocationPolicy, RiskPolicy
from meridian.schemas import AccountSnapshot, AlphaScore, TargetPortfolio, TargetPosition


class PortfolioAllocator(Protocol):
    def allocate(
        self,
        alpha_scores: list[AlphaScore],
        market_state: dict[str, Decimal],
        account_state: AccountSnapshot,
        policy: RiskPolicy,
    ) -> TargetPortfolio: ...


class ModelUnavailableError(RuntimeError):
    pass


class DeterministicFallbackAllocator:
    name = "deterministic_alpha_volatility_fallback"
    version = "BASELINE_V1"

    def allocate(
        self,
        alpha_scores: list[AlphaScore],
        market_state: dict[str, Decimal],
        account_state: AccountSnapshot,
        policy: RiskPolicy,
    ) -> TargetPortfolio:
        positive = [
            score for score in alpha_scores if score.score > 0 and score.evidence_quality > 0
        ]
        selected = sorted(positive, key=lambda score: (-score.score, score.ticker))[
            : policy.max_number_positions
        ]
        if not selected:
            return TargetPortfolio(
                as_of=account_state.as_of,
                cash_weight=Decimal("1"),
                positions=(),
                allocator_name=self.name,
                allocator_version=self.version,
            )
        available = Decimal("1") - policy.min_cash_weight
        total = sum((score.score for score in selected), Decimal("0"))
        weights = [
            min(policy.max_position_weight, available * score.score / total) for score in selected
        ]
        invested = sum(weights, Decimal("0"))
        return TargetPortfolio(
            as_of=account_state.as_of,
            cash_weight=Decimal("1") - invested,
            positions=tuple(
                TargetPosition(
                    ticker=score.ticker,
                    target_weight=weight,
                    conviction=score.confidence,
                    rationale="Deterministic alpha-score weighted fallback.",
                )
                for score, weight in zip(selected, weights, strict=True)
            ),
            allocator_name=self.name,
            allocator_version=self.version,
        )


class FinRLXAllocator:
    name = "finrlx"

    def __init__(
        self, model_artifact: str | None = None, artifact_version: str | None = None
    ) -> None:
        self.model_artifact = model_artifact
        self.artifact_version = artifact_version

    def allocate(
        self,
        alpha_scores: list[AlphaScore],
        market_state: dict[str, Decimal],
        account_state: AccountSnapshot,
        policy: RiskPolicy,
    ) -> TargetPortfolio:
        if not self.model_artifact or not self.artifact_version:
            raise ModelUnavailableError("MODEL_UNAVAILABLE: no validated FinRL-X model artifact")
        raise ModelUnavailableError(
            "MODEL_UNAVAILABLE: FinRL-X inference is not validated for this universe"
        )


def allocate_with_fallback(
    alpha_scores: list[AlphaScore],
    market_state: dict[str, Decimal],
    account_state: AccountSnapshot,
    policy: RiskPolicy,
    allocation: AllocationPolicy,
) -> TargetPortfolio:
    if allocation.allocator_selection == "finrlx":
        try:
            return FinRLXAllocator().allocate(alpha_scores, market_state, account_state, policy)
        except ModelUnavailableError:
            pass
    return DeterministicFallbackAllocator().allocate(
        alpha_scores, market_state, account_state, policy
    )
