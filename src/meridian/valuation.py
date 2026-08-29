"""Deterministic mark-to-market valuation separate from brokerage position truth."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from meridian.schemas import AccountSnapshot, FreshnessState, MarketSnapshot


@dataclass(frozen=True)
class MarkedHolding:
    ticker: str
    quantity: Decimal
    marked_price: Decimal
    marked_value: Decimal


@dataclass(frozen=True)
class ValuedAccountState:
    holdings: tuple[MarkedHolding, ...]
    decision_nav: Decimal
    broker_reported_total_equity: Decimal
    nav_discrepancy: Decimal
    discrepancy_exceeds_tolerance: bool

    @classmethod
    def from_snapshot(
        cls, account: AccountSnapshot, quotes: dict[str, MarketSnapshot], tolerance: Decimal
    ) -> ValuedAccountState:
        marked = []
        for holding in account.holdings:
            quote = quotes.get(holding.ticker)
            if quote is None or quote.freshness_state in {
                FreshnessState.STALE,
                FreshnessState.UNKNOWN,
            }:
                raise ValueError(f"missing fresh quote for {holding.ticker}")
            if (
                quote.bid is not None
                and quote.ask is not None
                and quote.bid > 0
                and quote.ask >= quote.bid
            ):
                mark = (quote.bid + quote.ask) / Decimal("2")
            elif quote.last > 0:
                mark = quote.last
            else:
                raise ValueError(f"missing valid mark price for {holding.ticker}")
            marked.append(
                MarkedHolding(holding.ticker, holding.quantity, mark, holding.quantity * mark)
            )
        nav = account.cash + sum((item.marked_value for item in marked), Decimal("0"))
        discrepancy = abs(nav - account.total_equity)
        return cls(tuple(marked), nav, account.total_equity, discrepancy, discrepancy > tolerance)

    def value_for(self, ticker: str) -> Decimal:
        return next(
            (item.marked_value for item in self.holdings if item.ticker == ticker), Decimal("0")
        )
