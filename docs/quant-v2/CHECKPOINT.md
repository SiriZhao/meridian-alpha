# Quant V2 recoverable checkpoint

Resumed 2026-10-08. Code and diagnostic delivery: `8072e60`.
Frozen source validation: 913 passed, Ruff/Pyright/dependencies/CLI/isolated
paper acceptance PASS. Independent GitHub clone also passed 913 tests. Current
code push/PR Windows/Linux CI passed. Final status lives in ACCEPTANCE.md and
CHECKPOINT.json; evidence-only delivery ref is verified at handoff.

Checkout: `.worktrees/quant-engine-v2`, branch `codex/quant-engine-v2`.
Base: `414d869`, plus published Phase 4 foundation through `0e01944`.
Original checkout and its pending work are preserved. Use the isolated
checkout's `.venv/Scripts/python.exe`; never change the canonical runtime.

Baseline log: `.tmp/quant-v2/baseline.log`.
Implemented: PIT feature contracts, scoring/regime, constrained portfolios,
delayed walk-forward replay, immutable shadow and separate paper-review packet.
Quant tests cover anti-lookahead, missing data, costs, risk and isolation;
resumed corrections add caller-state, adjusted research contract, missing
benchmark/final marks, held metadata and projected sector checks. ADR is 0037.
The original checkout's additional uncommitted Phase 4 work remains excluded.
All 92 synthetic validation/test evaluations completed for 23 predeclared
variants/two folds. Five contracts and all 94 archived files/88 distinct
replays verified against the current engine. Branch pushed and SHA matched;
draft PR 3 uses base `feature/forward-evidence-alpha-lab-20261008`. Independent
clone replay matched every one of the 92 rows/88 distinct payloads. Engineering
is complete; preserve the recorded evidence and continue financial data work
as a separately reviewed experiment, never a synthetic-driven promotion.
Financial alpha status: ALPHA_NOT_YET_DEMONSTRATED. Paper candidate remains
INSUFFICIENT_EVIDENCE. The repeated public history audit rejected raw,
uncertified, currently retrieved bars for financial PIT evidence. Synthetic
experiments demonstrate reproducibility only. No canonical runtime writes.

Next financial work requires independently reviewed PIT prices/adjustment
vintages/actions/membership/metadata/calendar, a separately registered empirical
experiment and at least 252 unique OOS sessions/two folds. Do not promote V2
using synthetic results. Rollback/default is QUANT_V1_BASELINE with no account
migration or reset. The original worktree's two pending document edits remain.

User authorized development branch commit/push and optional PR, no merge.
GPT-6.1 Sol High requested; this session exposes no model-switch control, so
the active model selection cannot be independently verified or changed.
