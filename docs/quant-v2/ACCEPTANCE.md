# Quant V2 engineering acceptance

Validation date: 2026-10-08. Financial readiness: INSUFFICIENT_EVIDENCE.
Implementation is in the isolated `codex/quant-engine-v2` worktree; the original
checkout and its additional uncommitted Phase 4 changes were preserved.

## Completed local checks

- Published canonical hardening `414d869` and Phase 4 `09e95dd` integrated;
  merge commit `780320d` retains both histories. No history rewrite.
- Full Windows host validation: **875 passed in 148.53 seconds**; dependency
  integrity, Ruff, Pyright, CLI and optimized safe paper acceptance all PASS.
- 88 new quant cases cover golden factors, future-information invariance,
  missing/uncertified history, scoring, regime cutoff, constrained allocations,
  no-trade/cost/liquidity, delayed deterministic replay, immutable registries,
  review evidence, metadata, rollback and unchanged V1 orders.
- Safe acceptance used two disposable synthetic scenarios: PAPER_NO_TRADE
  (zero orders/fills) and PAPER_READY (one synthetic order/fill); both repeat
  attempts returned PAPER_ALREADY_EXECUTED. Fresh-process and report consistency
  checks passed. Production market-session gates remain enabled.
- Frozen diagnostic: **92/92 evaluations completed**, 23 predeclared variants,
  two chronological folds, validation and test. All inputs SYNTHETIC_DIAGNOSTIC.
  Content-addressed deduplication stores 88 unique replays for the 92 rows.
- Skill package built and package-root validator passed (10 files).
- Review packet remains non-executing; candidate mode does not replace V1.

## Remaining delivery verification

Fresh clone, Windows/Linux GitHub Actions and exact remote HEAD verification
are pending publication. This document will be updated from actual results.

## Safety and operational limits

No canonical Doctor, canonical paper run, runtime write probe, migration,
reset or strategy promotion was executed. No broker interface or brokerage
credential was introduced. Canonical runtime/database were untouched by this
work; public-history reads wrote only this worktree's audit artifacts.
No real AccountSnapshot is persisted in diagnostics or committed files.

Shipped `policies/quant.yaml` is QUANT_V1_BASELINE with paper_approved=false.
Shadow failures are isolated; public quotes remain uncertified. Switching back
to V1 requires only that baseline setting, no ledger migration. Financial OOS
requires certified PIT prices/actions/membership/metadata, at least 252 unique
sessions across two folds and a separate human-approved paper review.

GPT-6.1 Sol High was requested, but this session exposes no model-switch
control; that exact model selection was not independently verified. No claim
of a ten-hour uninterrupted run or of profitable strategy acceptance is made.
