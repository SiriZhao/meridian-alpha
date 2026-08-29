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
2. Call `validate_host_account_snapshot`.
3. Call `run_host_daily_analysis` using the same envelope and current as-of
   time.
4. Present the returned account state, evidence, target portfolio, risk,
   readiness, and blockers.
5. Treat `ANALYSIS_ONLY` and `DRAFT` as non-enterable. Only
   `READY_FOR_MANUAL_ENTRY` is a manual-entry candidate, never an execution.
6. Never say `已执行` or that an order filled until a newer host snapshot proves
   the changed cash/holding state.

Read [workflow.md](references/workflow.md), [account-contract.md](references/account-contract.md),
and [safety.md](references/safety.md).