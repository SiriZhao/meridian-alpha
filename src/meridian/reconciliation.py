"""Reconcile targets only against a current AccountSnapshot, never recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from meridian.schemas import AccountSnapshot, FreshnessState, RunStatus, TargetPortfolio
from meridian.valuation import ValuedAccountState


@dataclass(frozen=True)
class PositionDelta:
    ticker: str
    actual_quantity: Decimal
    actual_value: Decimal
    actual_weight: Decimal
    target_value: Decimal
    target_weight: Decimal
    required_delta_value: Decimal


@dataclass(frozen=True)
class ReconciliationResult:
    status: RunStatus
    positions: tuple[PositionDelta, ...]
    warnings: tuple[str, ...]


class ReconciliationEngine:
    def reconcile(
        self,
        current_account_snapshot: AccountSnapshot,
        current_target_portfolio: TargetPortfolio,
        valued_state: ValuedAccountState | None = None,
    ) -> ReconciliationResult:
        if current_account_snapshot.freshness_state in {
            FreshnessState.STALE,
            FreshnessState.UNKNOWN,
        }:
            return ReconciliationResult(
                RunStatus.BLOCKED_STALE_ACCOUNT,
                (),
                ("Account snapshot freshness is not executable.",),
            )
        if current_account_snapshot.total_equity == 0:
            return ReconciliationResult(
                RunStatus.NO_CAPITAL, (), ("No capital available; no orders may be generated.",)
            )
        current = {holding.ticker: holding for holding in current_account_snapshot.holdings}
        targets = {position.ticker: position for position in current_target_portfolio.positions}
        nav = (
            valued_state.decision_nav
            if valued_state is not None
            else current_account_snapshot.total_equity
        )
        if nav <= 0:
            return ReconciliationResult(
                RunStatus.NO_CAPITAL, (), ("Decision NAV is zero; no orders may be generated.",)
            )
        deltas = []
        for ticker in sorted(set(current) | set(targets)):
            holding = current.get(ticker)
            position = targets.get(ticker)
            actual_quantity = holding.quantity if holding else Decimal("0")
            actual_value = (
                valued_state.value_for(ticker)
                if valued_state is not None
                else (holding.market_value if holding else Decimal("0"))
            )
            target_weight = position.target_weight if position else Decimal("0")
            target_value = target_weight * nav
            deltas.append(
                PositionDelta(
                    ticker,
                    actual_quantity,
                    actual_value,
                    actual_value / nav,
                    target_value,
                    target_weight,
                    target_value - actual_value,
                )
            )
        warnings = (
            ()
            if valued_state is None or not valued_state.discrepancy_exceeds_tolerance
            else ("Broker-reported equity differs from fresh marked NAV beyond tolerance.",)
        )
        return ReconciliationResult(RunStatus.DRAFT, tuple(deltas), warnings)
