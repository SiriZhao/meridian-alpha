# Quant V2 recoverable checkpoint

Resumed 2026-10-08. Frozen diagnostic delivery: `8072e60`; final integrated
source: `89a3554`. Final combined source validation: 925 passed in 175.54 seconds,
Ruff/Pyright/dependencies/contracts/CLI/isolated paper acceptance PASS. The
independent GitHub clone also passed 925 tests in 180.70 seconds. Earlier
Windows/Linux CI passed 913 tests before the final 12 foundation regressions.
Final combined push/PR CI both PASS: Windows 925, Ubuntu 923 plus two
Windows-only skips; packaging and manual-authority/replay negatives PASS.
Evidence lives in ACCEPTANCE.md and CHECKPOINT.json. Delivery ref is verified
at handoff.

Checkout: `.worktrees/quant-engine-v2`, branch `codex/quant-engine-v2`.
Base: `414d869`, plus published Phase 4 foundation through `fd7481d`.
Original checkout changes were preserved and later committed by their owning
task; the published result is integrated without history rewrite. Use the isolated
checkout's `.venv/Scripts/python.exe`; never change the canonical runtime.

Baseline log: `.tmp/quant-v2/baseline.log`.
Implemented: PIT feature contracts, scoring/regime, constrained portfolios,
delayed walk-forward replay, immutable shadow and separate paper-review packet.
Quant tests cover anti-lookahead, missing data, costs, risk and isolation;
resumed corrections add caller-state, adjusted research contract, missing
benchmark/final marks, held metadata and projected sector checks. ADR is 0037.
The original checkout is clean at the independently published Phase 4 checkpoint.
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
migration or reset. No original-worktree document edit was overwritten.

User authorized development branch commit/push and optional PR, no merge.
GPT-6.1 Sol High requested; this session exposes no model-switch control, so
the active model selection cannot be independently verified or changed.
