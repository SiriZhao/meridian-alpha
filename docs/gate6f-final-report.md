# Meridian Alpha — Gate 6F final report

## Release status

**MANUAL_ENTRY_AUTHORITY_CONVERGED**

Top-level authorization remains:

> **SHADOW / NOT AUTHORIZED FOR ENTRY**

`MANUAL_ENTRY_READY = NO` because no real Host smoke and no certified
execution-quote capability certificate are present in the current workspace.
No Schwab authentication, broker read/write, or real order was performed.

## Baseline

- Branch: `main`
- Gate 6E checkpoint: `4a93d14d53970436e5ac491858733030421bed0b`
- Full pytest: **262 passed**
- Ruff: **PASS**
- Pyright: **PASS**
- `git diff --check`: **PASS**
- Known P0: **0**
- Known P1: **0**

## Manual readiness authority

The single production-shaped chain is:

```text
fresh sanitized Host account truth
  + authoritative Security Master
  + current market state
  + certified research
  + certified ExecutionQuote
  + deterministic risk/reconciliation
  -> ManualReadinessCertificate(READY)
  -> build_manual_order_draft
  -> ManualOrderDraft(status=NOT_EXECUTED)
```

`ManualReadinessCertificate` is immutable and requires all seven literal PASS
gates: `ACCOUNT_READY`, `SECURITY_READY`, `MARKET_READY`, `RESEARCH_READY`,
`QUOTE_READY`, `RISK_READY`, and `RECONCILIATION_READY`. It also requires
non-empty lineage hashes and an execution-quote certificate ID. FAIL or
DEGRADED never counts as PASS.

The legacy `OrderPlanner`, `attach_limit_prices`, and compatibility
`create_manual_order_draft` paths cannot issue production-shaped manual drafts:
MarketSnapshot-based output is forced to `DRAFT`, and the compatibility helper
always blocks without the sealed authority.

## Execution quote authority

Every quote is checked against its capability certificate for provider,
feed/plan, symbol/currency scope, capability-content hash, validity interval,
session semantics, timezone-aware timestamp, freshness, positive non-inverted
prices, and spread policy. Closed/unsupported sessions, stale/future/wide
quotes, wrong identity, and forged or mismatched certificates fail closed.

`ResearchMarketPrice`, `ValuationMark`, and `MarketSnapshot` remain research or
valuation inputs only. Deterministic code owns limit price, quantity, target
weight, cash, rounding, risk, and reconciliation. LLM output cannot provide
price, offset, TIF, or quantity.

## MCP and reporting

MCP `get_order_ticket` and `inspect_manual_draft` require a persisted READY
`ManualReadinessCertificate` and sealed `NOT_EXECUTED` drafts carrying quote
certificate IDs. A READY `DailyDecision` or a duck-typed status is not enough.
Reports and runbooks now show the single authority and exact blockers.

## Assumed-fill firewall

Creating or displaying a `ManualOrderDraft` never updates holdings or cash and
never implies a fill. Only a later sanitized `HostAccountSnapshotEnvelope` can
establish an external trade, fill, deposit, withdrawal, or corporate action.

## Tests and artifacts

The Gate 6F test module covers all seven gate failures/degradations, provider,
feed, symbol-scope, expiry, capability-hash, session, spread and freshness
failures, duck-typed certificates, MCP refusal, and no-fill side effects. The
machine-readable writer/readiness matrix is in
`reports/gate6f-manual-authority-matrix.json` with its review rendering in
`reports/gate6f-manual-authority-matrix.md`.

### Final fields

| Field | Result |
|---|---|
| MANUAL READINESS AUTHORITY | `ManualReadinessAuthority` only |
| LEGACY MARKETSNAPSHOT BYPASS | Blocked; diagnostic `DRAFT` only |
| EXECUTIONQUOTE REQUIRED | Yes |
| CAPABILITY CERTIFICATE REQUIRED | Yes; content hash verified |
| 7-GATE AGGREGATION | All seven literal PASS required |
| MCP AUTHORITY | Sealed certificate + draft required |
| ASSUMED FILL | Impossible; later Host snapshot only |
| MANUAL ENTRY READY | **NO** |
| BROKER | NONE |
| SCHWAB | NOT CONNECTED |
| ORDERS | ZERO |

No production manual ticket is displayed or authorized in this state.
