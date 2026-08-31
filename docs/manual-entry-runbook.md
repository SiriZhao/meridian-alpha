# Manual decision-support runbook

Manual entry is a human decision-support capability, never execution. The
following gates must all pass for a real manual-entry candidate:

- fresh synchronized Host account truth;
- explicitly loaded and verified authoritative Security Master;
- current market and certified research data;
- certified read-only execution quote with bid, ask, timestamp, session, currency,
  freshness, and documented feed semantics;
- deterministic risk and reconciliation checks.

Without both real Host input and a real quote certificate, the status remains
`BLOCKED` or `SHADOW`. Limit price, quantity, rounding, cash, and risk are owned
by deterministic code. LLM output can affect research alpha only. Any displayed
draft is `NOT_EXECUTED`; a later account snapshot is required to establish a fill.

## Single authority (Gate 6F)

The only production-shaped draft constructor is
`meridian.manual_authority.build_manual_order_draft`. It accepts a sealed
`ManualReadinessCertificate`, an identity-bound `ExecutionQuote`, and its
`ExecutionQuoteCapabilityCertificate`. The certificate must be READY and all
seven gates must be literal PASS. Provider, feed/plan, symbol/currency scope,
content hash, validity window, session, timestamp, freshness, spread, and
positive quote fields are checked again at draft time.

Legacy `MarketSnapshot` pricing and the compatibility helper in
`execution_quotes.py` are diagnostic-only and cannot issue a production draft.
MCP ticket inspection applies the same certificate requirement. The returned
draft is `NOT_EXECUTED`; no draft is ever applied to a portfolio. Only a later,
new sanitized Host snapshot can prove a fill or other account change.
