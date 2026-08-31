# Gate 6F manual authority matrix

**Status:** `CONVERGED_WITH_MANUAL_ENTRY_BLOCKED_UNTIL_REAL_GATES_PASS`
**Manual entry:** **NO**
**Authorization:** `SHADOW / NOT AUTHORIZED FOR ENTRY`

## Single authority

`meridian.manual_authority.ManualReadinessAuthority` is the only production
manual-entry authority. `build_manual_order_draft` requires a READY,
provenance-bound `ManualReadinessCertificate`, a matching certified
`ExecutionQuoteCapabilityCertificate`, and a validated current `ExecutionQuote`.
The resulting `ManualOrderDraft` is always `NOT_EXECUTED`.

## Seven-gate aggregation

| Account | Security | Market | Research | Quote | Risk | Reconciliation | Result |
|---|---|---|---|---|---|---|---|
| PASS | PASS | PASS | PASS | PASS | PASS | PASS | READY only with sealed certificate |
| any single FAIL | PASS | PASS | PASS | PASS | PASS | PASS | BLOCKED |
| any single DEGRADED | PASS | PASS | PASS | PASS | PASS | PASS | BLOCKED |
| multiple failures | mixed | mixed | mixed | mixed | mixed | mixed | BLOCKED |

Every single-gate failure and degradation is covered by the Gate 6F test matrix.
A duck-typed object with `status=READY` is rejected.

## Writer audit

| Path | Input | Can authorize production manual entry? | Result |
|---|---|---:|---|
| `manual_authority.build_manual_order_draft` | `ExecutionQuote` + capability certificate | YES | Sealed `ManualOrderDraft` (`NOT_EXECUTED`) |
| `OrderPlanner.plan` | `MarketSnapshot` | NO | Diagnostic `OrderDraft` (`DRAFT`) |
| `attach_limit_prices` | `MarketSnapshot` | NO | Forces `DRAFT` |
| legacy `create_manual_order_draft` | unsealed quote/readiness map | NO | Always blocks; compatibility only |
| MCP `get_order_ticket` | persisted run | NO without sealed artifacts | Returns blocker unless certificate and sealed drafts exist |

## Quote certification

Provider/feed/plan identity, exact scope, capability-content hash, validity
interval, session semantics, timestamp/freshness, positive non-inverted prices,
and spread policy are revalidated for every quote instance. Closed or
unsupported extended-hours sessions, stale/future quotes, wide/inverted quotes,
wrong symbols/currencies, and mismatched/forged certificates fail closed.

## Assumed-fill firewall

No manual draft updates holdings or cash. A recommendation, target, or draft is
never a fill. Only a later sanitized `HostAccountSnapshotEnvelope` can establish
external account state.

## Validation

- Targeted Gate 6F authority tests: **20 passed**
- Full regression: **262 passed**
- Ruff: **PASS**
- Pyright: **PASS**
- `git diff --check`: **PASS**
- Known P0: **0**
- Known P1: **0**

The system remains blocked from manual entry until actual Host truth,
authoritative identity, certified research, risk/reconciliation, and a valid
execution quote certificate are supplied in one run.
