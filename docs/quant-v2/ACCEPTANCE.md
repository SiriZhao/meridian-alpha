# Quant V2 engineering acceptance

Validation date: 2026-10-08. Engineering: ENGINEERING_COMPLETE.
Financial result: ALPHA_NOT_YET_DEMONSTRATED. Paper readiness: INSUFFICIENT_EVIDENCE.
Implementation is in the isolated `codex/quant-engine-v2` worktree. The original
checkout's pending Phase 4 documents were preserved, subsequently committed by
their owning task, and integrated with its published foundation through `fd7481d`.

## Completed local checks

- Published canonical/provider/persistence foundation and Phase 4 through
  `fd7481d` integrated; merges `780320d`/`26abadd`/`89a3554` retain histories.
  No rewrite. The final integration includes Linux retained-zombie liveness
  handling and the inception-calendar qualification guard.
- Frozen code/archive delivery HEAD: `8072e6091036b1aed240722257d77fa3b43b111d`.
  Final combined source HEAD: `89a3554728d041fde65d2c470d43ccd774011355`.
  The integrated foundation adds 12 regression cases; the quant engine hash and
  frozen replay archive remain unchanged. Evidence-only delivery commits follow.
- Final combined Windows approved-host validation: **925 passed in 175.54
  seconds**; dependencies, Ruff, Pyright, contracts/archive, CLI and disposable
  paper/fresh-process/report consistency PASS.
- Full Windows approved-host validation: **913 passed in 345.69 seconds**;
  dependency integrity, Ruff, Pyright (zero errors/warnings), five-contract/full
  archive validation, CLI and optimized safe paper acceptance all PASS.
- 106 quant cases cover golden factors, future-information invariance,
  missing/uncertified history, scoring, regime cutoff, constrained allocations,
  no-trade/cost/liquidity, delayed deterministic replay, immutable registries,
  review evidence, metadata, rollback and unchanged V1 orders. Resumed guards
  include caller/default Decimal context and ordering, valid JSON adjusted PIT
  contracts, missing benchmark sessions/final marks, duplicate/future/held
  metadata and sector risk remaining after an incomplete SELL quote.
- Safe acceptance used two disposable synthetic scenarios: PAPER_NO_TRADE
  (zero orders/fills) and PAPER_READY (one synthetic order/fill); both repeat
  attempts returned PAPER_ALREADY_EXECUTED. Fresh-process and report consistency
  checks passed. Production market-session gates remain enabled.
- Frozen diagnostic: **92/92 evaluations completed**, 23 predeclared variants,
  two chronological folds, validation and test. All inputs SYNTHETIC_DIAGNOSTIC.
  Content-addressed deduplication stores 88 unique replays for the 92 rows.
- Skill package built and package-root validator passed (10 files).
- Review packet remains non-executing; candidate mode does not replace V1.

## Independent GitHub fresh clone and replay

The branch was cloned from GitHub at `8072e60` into a new isolated directory.
Python 3.12.10, its own `.venv`, frozen uv.lock and 48 installed packages were
used; imports were asserted to resolve inside the clone rather than the source
worktree. Full validation: **913 passed in 374.03 seconds**; dependencies,
Ruff/Pyright, contracts/archive, CLI, isolated paper, fresh-process and report
consistency PASS. Clone status was clean; Windows review packaging also PASS.

The same independent GitHub clone was fast-forwarded from the remote branch to
final combined source `89a3554` using its existing frozen-lock environment.
Imports and interpreter still resolve inside that clone; Git status is clean.
Final combined validation: **925 passed in 180.70 seconds**, dependencies,
Ruff/Pyright, contracts/archive, CLI and isolated paper/report/fresh-process PASS.

The clone's CLI independently replayed the saved dataset and frozen plan. All
92 evaluation rows and all 88 distinct replay payloads matched the published
archive exactly, including the summary identity. No newly fitted parameter or
changed OOS selection was used. The archive contains 94 JSON files.

## Current code CI and Git delivery

Normal push and stacked draft [PR 3](https://github.com/SiriZhao/meridian-alpha/pull/3)
preserve main and history. PR base is `feature/forward-evidence-alpha-lab-20261008`.
Local/remote code/archive SHA matched `8072e60`; source checkpoint and independent
clone match the same code. Main remains `1d7e064`; no automatic merge.

Both [push CI 37744718825](https://github.com/SiriZhao/meridian-alpha/actions/runs/37744718825)
and [PR CI 37744910303](https://github.com/SiriZhao/meridian-alpha/actions/runs/37744910303)
completed successfully for that exact SHA. Raw push logs record Windows
**913 passed in 225.94 seconds**, Ubuntu **911 passed, two platform skips in
206.65 seconds**. Skips are only the Windows PowerShell 5 launcher and Windows
packaging helper; Windows runs both. No quant test is skipped/xfail.
Both platforms also pass 21 manual-authority negatives, eight replay-integrity
checks and skill packaging; Windows review packaging PASS. Final evidence-tip
remote SHA/CI are checked at handoff rather than embedded as self-referential
commit hashes. The validated engine hash is unchanged by documentation commits.

Final combined source `89a3554` is also verified on both platforms:
[push CI 37747608628](https://github.com/SiriZhao/meridian-alpha/actions/runs/37747608628)
and [PR CI 37747616070](https://github.com/SiriZhao/meridian-alpha/actions/runs/37747616070)
both SUCCESS. Raw push logs record Windows **925 passed in 236.75 seconds** and
Ubuntu **923 passed, two Windows-only skips in 205.44 seconds**. Both platforms
pass manual-authority negatives, replay integrity, artifact and skill packaging;
Windows source-review packaging PASS. No Quant case is skipped or xfailed.
The final delivery commit contains only these evidence/checkpoint documents;
its exact remote SHA and its own CI are checked before handoff.

Important delivery commits: `27fb2f9` engine/integration, `32f6e97` published
laboratory integration, `211cb37` Linux exit-race backport, `26abadd` latest
published foundation merge, `f40282f` numeric/PIT/projection repairs, `8072e60`
complete frozen registry and research limitations.
`89a3554` integrates the final published foundation through `fd7481d` without
reverting the owning task's documents or modifying the Quant engine.

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

Repeated real public audit: 825 rows each for AAPL/MSFT/SPY, 2023-06-26 to
2026-10-07, retrieved 2026-10-08 07:30 UTC. All raw, uncertified and zero
historically-known-at-close rows; feature gates rejected them. Adjustment
vintage/actions/membership/metadata/calendar and authenticated provenance are
not demonstrated. Synthetic diagnostics cannot prove OOS alpha, overfitting,
survivorship or robustness in actual market regimes. Current candidate remains
INSUFFICIENT_EVIDENCE; automatic promotion stays disabled.

GPT-6.1 Sol High was requested, but this session exposes no model-switch
control; that exact model selection was not independently verified. No claim
of a ten-hour uninterrupted run or of profitable strategy acceptance is made.
