---
name: meridian-alpha
description: Safely validate a sanitized HostAccountSnapshotEnvelope and run read-only US-equity Meridian decision support. Use for daily shadow analysis, certified SEC evidence review, Quant plus DeepSeek research, and manual-entry readiness checks without broker login or order execution.
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
3. If the read-only MCP surface is available, call
   `validate_host_account_snapshot` (or `validate_account_snapshot` for a
   normalized snapshot).
4. Call `run_host_daily_analysis` (or `run_daily_analysis`) using the same
   envelope and current as-of time.
5. Present the returned account state, evidence, target portfolio, risk,
   readiness, and blockers.
6. Treat `ANALYSIS_ONLY` and `DRAFT` as non-enterable. Only
   `READY_FOR_MANUAL_ENTRY` is a manual-entry candidate, never an execution.
7. Never say `已执行` or that an order filled until a newer host snapshot proves
   the changed cash/holding state.

Execution quotes are a separate certified capability. `meridian
quote-preflight` reports candidate-provider health only; without a verified
certificate, `QUOTE_READY` and manual entry remain blocked.

## Capability detection

At runtime distinguish `HOST_ACCOUNT_TOOL_AVAILABLE`,
`PYTHON_RUNTIME_AVAILABLE`, `NETWORK_AVAILABLE`, `CERTIFIED_QUOTE_AVAILABLE`,
and `LIVE_DEEPSEEK_AVAILABLE`. Never assume any capability exists. If a
required capability is unavailable, fail closed with the exact blocker; do not
fabricate prices, account state, evidence, or calculations. A GitHub checkout
is not a runtime requirement for this Skill: use package-relative references
and the Host-provided input contract.

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

## Gate 6F manual-entry authority

Never infer manual-entry readiness from `DailyDecision.overall_status` alone.
Require a concrete READY `ManualReadinessCertificate` with all seven gates and a
matching certified `ExecutionQuoteCapabilityCertificate`. The only
production-shaped constructor is `build_manual_order_draft`; its result is
`NOT_EXECUTED`. MarketSnapshot/research prices and valuation marks are
analysis-only, and MCP must return a blocker when the sealed certificate or
quote certificate is absent. A later sanitized Host snapshot, never a draft,
proves an external fill.

## V1 frozen daily workflow

Use `meridian daily` as the only supported production-style command. Receive a
sanitized Host snapshot, validate it, run the selected safe profile, and return
the sanitized report, evidence lineage, and target portfolio. Return a manual
draft only when a sealed `ManualReadinessCertificate` is `READY` and the exact
`ExecutionQuote` is backed by a valid capability certificate. Otherwise return
explicit blockers. The read-only MCP surface is limited to account validation,
daily analysis/reporting, evidence/research/portfolio inspection, manual-draft
inspection, and provider health. There is no broker tool, `AUTO_EXECUTION`
profile, broker login, Schwab authentication, order operation, or assumed fill.

## Mobile/Host workflow

Obtain an authorized sanitized Host snapshot when the Host exposes that
capability; otherwise request the user to provide one. Validate it, run the
safe profile, and return the Chinese daily report, evidence lineage, and target
portfolio. Only a sealed `ManualReadinessCertificate` with all seven gates plus
a matching `ExecutionQuoteCapabilityCertificate` can produce a
`ManualOrderDraft`; every draft is `NOT_EXECUTED` and requires human review.

## HOST_NATIVE mode and portable invocation

Use `HOST_NATIVE` when the host can provide capabilities directly. Detect each
capability rather than assuming it: accept only an authorized sanitized
`HostAccountSnapshotEnvelope`, execute deterministic Meridian code only when
the Python runtime and project core are actually available, and fail closed
with `MERIDIAN_RUNTIME_UNAVAILABLE` otherwise. The portable
`scripts/preflight.py` and `scripts/run_daily.py` use no shell-specific startup
and delegate all financial calculations to the project-owned core. See
[runtime-dependencies.md](references/runtime-dependencies.md).

## Invocation triggers

For requests such as “run Meridian”, “analyze my portfolio”, “today's Meridian
report”, or “large-cap dip-buy analysis”, follow capability preflight →
sanitized account truth → certified SEC/market data → deterministic core →
certified research → Chinese report. For a real account request, never infer
holdings from conversation history. If the runtime is unavailable, state
`MERIDIAN_RUNTIME_UNAVAILABLE` and identify the missing capability; do not
recreate investment calculations in prose.

For a portable capability check, run `python scripts/preflight.py`. To request
the safe core-delegating wrapper, run `python scripts/run_daily.py --profile
TEST` (or `REPLAY` with a matching frozen input). The wrapper emits sanitized
JSON followed by the Chinese mobile report; it never treats an unavailable
runtime as completed analysis.
