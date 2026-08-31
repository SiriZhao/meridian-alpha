# Daily operator runbook

1. Obtain a new sanitized `HostAccountSnapshotEnvelope` from an authorized host.
   Do not include account numbers, credentials, tokens, or raw connector payloads.
2. Validate the envelope and freshness with `meridian host-smoke <file>`.
3. Run `meridian daily --account-fixture <sanitized-file> --date <ISO-time>` in
   the intended profile. The default is `TEST`; use `SHADOW_LIVE` only with the
   existing explicit research opt-in.
4. Read the leading report status (`BLOCKED`, `ANALYSIS_ONLY`, `SHADOW`, or
   `READY_FOR_MANUAL_ENTRY`). A shadow result is never an order.
5. Review account truth, certified evidence, quant output, risk, reconciliation,
   provider health, and the target portfolio. Never infer a fill from a target.
6. If a manual-entry candidate is ever shown, independently verify the current
   account and certified execution quote immediately before human entry.

There is no automatic execution profile. A later host snapshot is the only proof
of an external trade, fill, deposit, withdrawal, or corporate action.

## Gate 6F authority check

Before showing anything that resembles a manual ticket, confirm that the same
run has a READY `ManualReadinessCertificate` with all seven gates:
`ACCOUNT_READY`, `SECURITY_READY`, `MARKET_READY`, `RESEARCH_READY`,
`QUOTE_READY`, `RISK_READY`, and `RECONCILIATION_READY`. The certificate must
reference the exact certified `ExecutionQuote` capability certificate.

A `MarketSnapshot`, research price, valuation mark, or legacy `OrderDraft` can
only produce analysis/diagnostic output. If any gate is FAIL or DEGRADED, show
`BLOCKED` or `ANALYSIS_ONLY` and list the blocker. A `ManualOrderDraft` is
always `NOT_EXECUTED`; never update the account or infer a fill from it.

## V1 frozen daily operation

Use the single supported command:

```text
meridian daily [--account-fixture <sanitized AccountSnapshot>] [--date <ISO>] [--profile TEST|REPLAY|SHADOW_LIVE|MANUAL_DECISION_SUPPORT]
```

The safe default is a local `TEST` fixture. `SHADOW_LIVE` is explicit opt-in;
`MANUAL_DECISION_SUPPORT` is blocked until a real Host snapshot, authoritative
identity, certified quote, risk, and reconciliation certificate are present.
Each run writes a sanitized package under `runs/<date>/<run_id>/` and appends
shadow ledgers. Never treat a target or draft as traded.
