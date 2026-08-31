"""Deterministic order sizing, conservative limits, and projected validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from meridian.config import ExecutionPolicy, RiskPolicy
from meridian.reconciliation import ReconciliationResult
from meridian.schemas import (
    AccountSnapshot,
    FreshnessState,
    MarketSnapshot,
    OrderDraft,
    RunStatus,
    Side,
)
from meridian.valuation import ValuedAccountState


@dataclass(frozen=True)
class LimitPriceResult:
    preferred_limit: Decimal | None
    max_acceptable_buy_price: Decimal | None
    min_acceptable_sell_price: Decimal | None
    reason: str
    status: RunStatus


class LimitPriceEngine:
    version = "BASELINE_V1"

    def calculate(
        self, side: Side, quote: MarketSnapshot, policy: ExecutionPolicy
    ) -> LimitPriceResult:
        if quote.freshness_state in {FreshnessState.STALE, FreshnessState.UNKNOWN}:
            return LimitPriceResult(
                None,
                None,
                None,
                "Quote freshness is not executable.",
                RunStatus.BLOCKED_STALE_MARKET,
            )
        if (
            quote.last <= 0
            or quote.previous_close <= 0
            or quote.atr14 is None
            or quote.atr14 <= 0
            or quote.vwap is None
            or quote.bid is None
            or quote.ask is None
        ):
            return LimitPriceResult(
                None, None, None, "Quote is incomplete; recalculation is required.", RunStatus.DRAFT
            )
        if quote.gap_percent is not None and abs(quote.gap_percent) > policy.max_gap_percent:
            return LimitPriceResult(
                None, None, None, "Overnight gap exceeds policy; recalculate.", RunStatus.DRAFT
            )
        spread = (quote.ask - quote.bid) / quote.last
        if spread > policy.max_spread_percent:
            return LimitPriceResult(
                None, None, None, "Spread exceeds policy; keep as draft.", RunStatus.DRAFT
            )
        if side is Side.BUY:
            preferred = min(quote.ask, quote.vwap)
            cap = min(
                quote.ask * (Decimal("1") + policy.max_chase_percent),
                quote.last * (Decimal("1") + policy.max_chase_percent),
            ).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
            return LimitPriceResult(
                preferred.quantize(Decimal("0.0001"), rounding=ROUND_DOWN),
                cap,
                None,
                "BASELINE_V1 buy limit bounded by ask/last and max chase policy.",
                RunStatus.READY_FOR_MANUAL_ENTRY,
            )
        preferred = max(quote.bid, quote.vwap)
        floor = max(
            quote.bid * (Decimal("1") - policy.max_chase_percent),
            quote.last * (Decimal("1") - policy.max_chase_percent),
        ).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        return LimitPriceResult(
            preferred.quantize(Decimal("0.0001"), rounding=ROUND_DOWN),
            None,
            floor,
            "BASELINE_V1 sell limit bounded by bid/last and max chase policy.",
            RunStatus.READY_FOR_MANUAL_ENTRY,
        )


class OrderPlanner:
    def plan(
        self,
        account: AccountSnapshot,
        reconciliation: ReconciliationResult,
        quotes: dict[str, MarketSnapshot],
        policy: ExecutionPolicy,
        risk_policy: RiskPolicy | None = None,
        decision_nav: Decimal | None = None,
    ) -> tuple[OrderDraft, ...]:
        if reconciliation.status in {RunStatus.NO_CAPITAL, RunStatus.BLOCKED_STALE_ACCOUNT}:
            return ()
        engine = LimitPriceEngine()
        available_cash = account.cash * (Decimal("1") - policy.transaction_reserve_percent)
        drafts = []
        # Sells are planned first for risk reduction, but proceeds are deliberately not added to buy cash.
        for delta in sorted(
            (d for d in reconciliation.positions if d.required_delta_value < 0),
            key=lambda d: d.ticker,
        ):
            quote = quotes.get(delta.ticker)
            result = engine.calculate(Side.SELL, quote, policy) if quote else None
            if (
                quote is None
                or result is None
                or result.status is not RunStatus.READY_FOR_MANUAL_ENTRY
                or result.min_acceptable_sell_price is None
            ):
                continue
            price = result.min_acceptable_sell_price
            qty = min(
                delta.actual_quantity,
                (-delta.required_delta_value / price).quantize(Decimal("1"), rounding=ROUND_DOWN),
            )
            if qty <= 0 or qty * price < policy.minimum_order_notional:
                continue
            drafts.append(
                OrderDraft(
                    ticker=delta.ticker,
                    side=Side.SELL,
                    quantity=qty,
                    preferred_limit=result.preferred_limit,
                    min_acceptable_sell_price=price,
                    target_weight=delta.target_weight,
                    current_weight=delta.actual_weight,
                    estimated_notional=qty * price,
                    time_in_force=policy.time_in_force,
                    status=RunStatus.DRAFT,
                    reason="Deterministic reduction to approved target.",
                )
            )
        for delta in sorted(
            (d for d in reconciliation.positions if d.required_delta_value > 0),
            key=lambda d: d.ticker,
        ):
            quote = quotes.get(delta.ticker)
            result = engine.calculate(Side.BUY, quote, policy) if quote else None
            if (
                quote is None
                or result is None
                or result.status is not RunStatus.READY_FOR_MANUAL_ENTRY
                or result.max_acceptable_buy_price is None
            ):
                continue
            worst = result.max_acceptable_buy_price
            budget = min(delta.required_delta_value, available_cash)
            qty = (budget / worst).quantize(Decimal("1"), rounding=ROUND_DOWN)
            if qty <= 0 or qty * worst < policy.minimum_order_notional:
                continue
            notional = qty * worst
            available_cash -= notional
            drafts.append(
                OrderDraft(
                    ticker=delta.ticker,
                    side=Side.BUY,
                    quantity=qty,
                    preferred_limit=result.preferred_limit,
                    max_acceptable_buy_price=worst,
                    target_weight=delta.target_weight,
                    current_weight=delta.actual_weight,
                    estimated_notional=notional,
                    time_in_force=policy.time_in_force,
                    status=RunStatus.DRAFT,
                    reason="Deterministic purchase sized at worst-case limit; sell proceeds not assumed.",
                )
            )
        if risk_policy and decision_nav and decision_nav > 0:
            drafts = self._apply_caps(drafts, risk_policy, decision_nav)
        return tuple(drafts)

    def _apply_caps(
        self, drafts: list[OrderDraft], policy: RiskPolicy, nav: Decimal
    ) -> list[OrderDraft]:
        capped = []
        max_notional = nav * policy.max_single_order_nav_percent
        turnover_budget = nav * policy.max_daily_turnover
        used = Decimal("0")
        for draft in drafts:
            unit = (
                draft.max_acceptable_buy_price
                if draft.side is Side.BUY
                else draft.min_acceptable_sell_price
            )
            if unit is None:
                continue
            qty = min(
                draft.quantity, (max_notional / unit).quantize(Decimal("1"), rounding=ROUND_DOWN)
            )
            qty = min(
                qty, ((turnover_budget - used) / unit).quantize(Decimal("1"), rounding=ROUND_DOWN)
            )
            if qty <= 0:
                continue
            notion = qty * unit
            used += notion
            reason = draft.reason
            if qty < draft.quantity:
                reason += " Reduced by max_single_order_nav_percent/max_daily_turnover constraints."
            capped.append(
                draft.model_copy(
                    update={"quantity": qty, "estimated_notional": notion, "reason": reason}
                )
            )
        return capped


def attach_limit_prices(
    drafts: tuple[OrderDraft, ...], quotes: dict[str, MarketSnapshot], policy: ExecutionPolicy
) -> tuple[OrderDraft, ...]:
    engine = LimitPriceEngine()
    priced = []
    for draft in drafts:
        quote = quotes.get(draft.ticker)
        payload = draft.model_dump()
        if quote is None:
            payload.update({"reason": f"{draft.reason} Missing quote.", "status": RunStatus.DRAFT})
        else:
            result = engine.calculate(draft.side, quote, policy)
            payload.update(
                {
                    "preferred_limit": result.preferred_limit,
                    "max_acceptable_buy_price": result.max_acceptable_buy_price,
                    "min_acceptable_sell_price": result.min_acceptable_sell_price,
                    "reason": f"{draft.reason} {result.reason}",
                    "status": RunStatus.DRAFT,
                }
            )
            unit = (
                result.max_acceptable_buy_price
                if draft.side is Side.BUY
                else result.min_acceptable_sell_price
            )
            if unit is not None:
                payload["estimated_notional"] = (draft.quantity * unit).quantize(Decimal("0.0001"))
        priced.append(OrderDraft.model_validate(payload))
    return tuple(priced)


@dataclass(frozen=True)
class ProjectionReport:
    valid: bool
    projected_cash: Decimal
    violations: tuple[str, ...]
    projected_holdings: dict[str, Decimal] | None = None
    projected_market_value: Decimal = Decimal("0")
    projected_position_count: int = 0


class ProjectedPortfolioValidator:
    def validate(
        self,
        account: AccountSnapshot,
        orders: tuple[OrderDraft, ...],
        decision_nav: Decimal,
        min_cash_weight: Decimal = Decimal("0"),
        max_position_weight: Decimal | None = None,
        max_number_positions: int | None = None,
        valued_state: ValuedAccountState | None = None,
        sector_map: dict[str, str] | None = None,
        max_sector_weight: Decimal | None = None,
    ) -> ProjectionReport:
        holdings = {h.ticker: h.quantity for h in account.holdings}
        values = {
            h.ticker: (
                valued_state.value_for(h.ticker) if valued_state is not None else h.market_value
            )
            for h in account.holdings
        }
        cash = account.cash
        violations = []
        seen = set()
        for order in orders:
            if order.ticker in seen:
                violations.append("duplicate order")
            seen.add(order.ticker)
            unit = (
                order.max_acceptable_buy_price
                if order.side is Side.BUY
                else order.min_acceptable_sell_price
            )
            if unit is None:
                violations.append(f"{order.ticker}: missing conservative price")
                continue
            if order.side is Side.SELL:
                if order.quantity > holdings.get(order.ticker, Decimal("0")):
                    violations.append(f"{order.ticker}: oversell")
                holdings[order.ticker] = holdings.get(order.ticker, Decimal("0")) - order.quantity
                cash += order.quantity * unit
                values[order.ticker] = max(
                    Decimal("0"), values.get(order.ticker, Decimal("0")) - order.quantity * unit
                )
            else:
                cost = order.quantity * unit
                # Always project BUY effects before evaluating violations so
                # later orders observe cumulative state.
                if cost > cash:
                    violations.append(f"{order.ticker}: negative cash")
                cash -= cost
                holdings[order.ticker] = holdings.get(order.ticker, Decimal("0")) + order.quantity
                values[order.ticker] = values.get(order.ticker, Decimal("0")) + cost
        if cash < 0:
            violations.append("projected cash negative")
        if decision_nav > 0 and cash / decision_nav < min_cash_weight:
            violations.append("min cash violation")
        if (
            max_number_positions is not None
            and sum(1 for q in holdings.values() if q > 0) > max_number_positions
        ):
            violations.append("max number positions")
        if sector_map and max_sector_weight is not None and decision_nav > 0:
            sector_values: dict[str, Decimal] = {}
            for ticker, value in values.items():
                sector = sector_map.get(ticker)
                if sector is not None:
                    sector_values[sector] = sector_values.get(sector, Decimal("0")) + value
            if any(value / decision_nav > max_sector_weight for value in sector_values.values()):
                violations.append("sector constraint violation")
        if (
            max_position_weight is not None
            and decision_nav > 0
            and any(v / decision_nav > max_position_weight for v in values.values())
        ):
            violations.append("position cap violation")
        return ProjectionReport(
            not violations,
            cash,
            tuple(dict.fromkeys(violations)),
            dict(holdings),
            sum(values.values(), Decimal("0")),
            sum(1 for quantity in holdings.values() if quantity > 0),
        )
