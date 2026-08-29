# ADR-002: Marked valuation and conservative execution constraints

Status: Accepted (Gate 1.5)

## Decision

`AccountSnapshot` remains authoritative for account existence, cash, and share
quantities. Current executable valuation is derived separately by
`ValuedAccountState` from fresh `MarketSnapshot` marks. The regular-session mark
is the bid/ask midpoint when both are positive and ordered; otherwise `last` is
used only when positive. Missing or stale marks fail closed.

Decision NAV is cash plus marked holdings. Broker-reported equity is preserved
for diagnostics. A configurable `nav_discrepancy_tolerance` blocks executable
output when the absolute difference exceeds tolerance.

Order sizing computes the limit envelope before quantities. BUY quantities use
`max_acceptable_buy_price`; same-day SELL proceeds are never used to fund BUYs.
The transaction reserve is removed from current cash before sizing.

For every order, conservative notional is quantity times max acceptable BUY
price or min acceptable SELL price. Single-order and turnover constraints use
that notional. Gross turnover is
`sum(conservative absolute order notionals) / decision_nav`. The deterministic
priority is risk-reducing SELLs, reductions, then BUYs in ticker order; excess
quantities are reduced and the reason is recorded.

Projected portfolio validation runs after final pricing and quantities. Any
negative cash, oversell, leverage, cap, cash-floor, duplicate, or affordability
violation prevents `READY_FOR_MANUAL_ENTRY`.

## Consequences

Fresh quote data is required for current valuation even when brokerage-reported
market values are present. `NO_ACTION` is the only no-order terminal state;
`READY_FOR_MANUAL_ENTRY` always contains at least one executable draft.
