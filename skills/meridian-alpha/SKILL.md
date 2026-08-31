---
name: meridian-alpha
description: Safely validate a sanitized HostAccountSnapshotEnvelope and run read-only Meridian analysis without connecting to a broker or executing orders.
---

# Meridian Alpha Host workflow

When a user asks to run Meridian, the Host—not Meridian Python—may obtain
current facts from an authorized account source. Never name, configure, or
invoke a particular brokerage, finance SDK, bank SDK, login, credential, or
account number.

1. Sanitize current facts into `HostAccountSnapshotEnvelope`.
2. For local CLI review, run `meridian host-smoke <file>`; it performs schema,
   sensitive-key, freshness, identity, normalization, and shared-analysis
   checks without connecting to an account source.
3. Call `validate_host_account_snapshot`.
4. Call `run_host_daily_analysis` using the same envelope and current as-of
   time.
5. Present the returned account state, evidence, target portfolio, risk,
   readiness, and blockers.
6. Treat `ANALYSIS_ONLY` and `DRAFT` as non-enterable. Only
   `READY_FOR_MANUAL_ENTRY` is a manual-entry candidate, never an execution.
7. Never say `已执行` or that an order filled until a newer host snapshot proves
   the changed cash/holding state.

Execution quotes are a separate certified capability. `meridian
quote-preflight` reports candidate-provider health only; without a verified
certificate, `QUOTE_READY` and manual entry remain blocked.

Read [workflow.md](references/workflow.md), [account-contract.md](references/account-contract.md),
and [safety.md](references/safety.md).

## Gate 6D/6E operator profiles

Use `TEST` for fixtures, `REPLAY` for frozen artifacts, `SHADOW_LIVE` only with
explicit bounded live research opt-in, and `MANUAL_DECISION_SUPPORT` only after
real Host/account, authoritative identity, quote, risk, and reconciliation gates
pass. There is no `AUTO_EXECUTION` profile. Every report begins with one of
`BLOCKED`, `ANALYSIS_ONLY`, `SHADOW`, or `READY_FOR_MANUAL_ENTRY`.

The long-shadow ledger separates recommendation, target, and later outcome. It
never implies a fill. FinRL-X is an optional isolated allocator challenger only;
`MODEL_UNAVAILABLE` is the correct status without a real OOS-validated artifact.
