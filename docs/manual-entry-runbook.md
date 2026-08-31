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
