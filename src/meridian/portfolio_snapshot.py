"""Immutable, read-only portfolio facts for research and synthesis."""

from __future__ import annotations

from decimal import Decimal

from pydantic import AwareDatetime, Field, model_validator

from meridian.host_account import HostAccountSnapshotEnvelope, HostCoverageStatus
from meridian.schemas import AccountSnapshot, StableModel


class PortfolioPositionSnapshot(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    quantity: Decimal = Field(ge=0)
    cost_basis: Decimal | None = Field(default=None, ge=0)
    market_value: Decimal | None = Field(default=None, ge=0)
    unrealized_pnl: Decimal | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=1)


class PortfolioSnapshot(StableModel):
    """Frozen portfolio view. Absence is represented by ``None``, never flat."""

    snapshot_id: str
    timestamp: AwareDatetime
    cash: Decimal = Field(ge=0)
    equity: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    positions: tuple[PortfolioPositionSnapshot, ...] = ()
    cash_weight: Decimal = Field(ge=0, le=1)
    concentration: Decimal = Field(ge=0, le=1)
    source_kind: str
    authority: str = "READ_ONLY_RESEARCH_CONTEXT"

    @model_validator(mode="after")
    def coherent_weights(self) -> PortfolioSnapshot:
        if self.equity < self.cash:
            raise ValueError("PORTFOLIO_EQUITY_BELOW_CASH")
        if len({item.ticker for item in self.positions}) != len(self.positions):
            raise ValueError("PORTFOLIO_DUPLICATE_POSITION")
        return self

    @classmethod
    def from_host_envelope(cls, envelope: HostAccountSnapshotEnvelope) -> PortfolioSnapshot:
        if envelope.coverage_status is not HostCoverageStatus.COMPLETE:
            raise ValueError("PORTFOLIO_SNAPSHOT_INCOMPLETE")
        positions = []
        for item in envelope.positions:
            weight = (
                item.market_value / envelope.total_equity
                if item.market_value is not None and envelope.total_equity
                else None
            )
            unrealized = (
                item.market_value - item.cost_basis
                if item.market_value is not None and item.cost_basis is not None
                else None
            )
            positions.append(
                PortfolioPositionSnapshot(
                    ticker=item.ticker,
                    quantity=item.quantity,
                    cost_basis=item.cost_basis,
                    market_value=item.market_value,
                    unrealized_pnl=unrealized,
                    weight=weight,
                )
            )
        weights = [item.weight for item in positions if item.weight is not None]
        return cls(
            snapshot_id=envelope.snapshot_id,
            timestamp=envelope.as_of,
            cash=envelope.cash,
            equity=envelope.total_equity,
            currency=envelope.base_currency,
            positions=tuple(positions),
            cash_weight=envelope.cash / envelope.total_equity
            if envelope.total_equity
            else Decimal("0"),
            concentration=max(weights, default=Decimal("0")),
            source_kind=envelope.source_kind,
        )

    @classmethod
    def from_account_snapshot(cls, account: AccountSnapshot) -> PortfolioSnapshot:
        positions = []
        for item in account.holdings:
            weight = item.market_value / account.total_equity if account.total_equity else None
            unrealized = (
                item.market_value - item.cost_basis if item.cost_basis is not None else None
            )
            positions.append(
                PortfolioPositionSnapshot(
                    ticker=item.ticker,
                    quantity=item.quantity,
                    cost_basis=item.cost_basis,
                    market_value=item.market_value,
                    unrealized_pnl=unrealized,
                    weight=weight,
                )
            )
        weights = [item.weight for item in positions if item.weight is not None]
        return cls(
            snapshot_id=account.snapshot_id,
            timestamp=account.as_of,
            cash=account.cash,
            equity=account.total_equity,
            currency=account.currency,
            positions=tuple(positions),
            cash_weight=account.cash / account.total_equity
            if account.total_equity
            else Decimal("0"),
            concentration=max(weights, default=Decimal("0")),
            source_kind=account.provider,
        )

    def research_view(self) -> dict[str, object]:
        """Sanitized facts only; no mutation or execution handle is exposed."""
        return self.model_dump(mode="json")
