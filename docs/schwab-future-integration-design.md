# Future broker integration design (not implemented)

This document is a boundary design only. No authentication, account adapter,
execution adapter, order transport, or credential handling is implemented in
Meridian. A future phase may be opened only after the manual decision-support
release candidate is stable, real Host smoke passes, execution quotes are
certified, multiple shadow sessions are observed, reconciliation is stable, P0 is
zero, and the user explicitly authorizes that phase.

The future layers are intentionally separate:

- `SchwabAuthBoundary` — OAuth authorization-code flow, token lifecycle,
  revocation, secure secret storage, and no token persistence in Meridian logs.
- `SchwabReadOnlyAccountAdapter` — sanitized account snapshots only.
- `SchwabExecutionAdapter` — a separately reviewed future boundary, disabled by
  default and outside the current product.
- `ExecutionIntent` — human-approved, idempotent intent with account/security,
  quantity, price, session, and policy hashes.
- `OrderSubmissionReceipt` / `BrokerOrderState` / `FillObservation` — explicit
  transport, acknowledgement, partial-fill, reject, cancel/replace, and later
  observed-state records; a recommendation is never a fill.
- `KillSwitch` — deterministic global and per-account halt, manual override,
  audit trail, and fail-closed recovery.

The review checklist must cover OAuth and secret lifecycle, idempotency and
duplicate protection, market-hours gates, account/quantity mismatch, reject and
partial-fill handling, cancel/replace, rate limits, disconnects, bounded retries,
kill switch, manual override, and immutable audit records. None of these
requirements authorizes implementation in Gate 6E.
## Gate 6I prerequisite freeze

This remains design-only: no Schwab authentication, account read, token
handling, broker SDK, order write, cancellation, or execution code is present.
A future broker phase cannot open until Gate 6F authority is stable, a real Host
smoke and certified ExecutionQuote pass, 5–10 shadow sessions are reviewed, no
P0 remains, manual v1 is stable, and the user explicitly authorizes a separate
Gate 7.
