# Mission 4 research terminal acceptance

Scope: existing V2.2 integration, research-only MCP, native explanation grounding,
bounded planner, structured brief, versioned Skill and Chinese terminal.
Optional general-purpose tool execution and a live financial/model evaluation
are outside the completed engineering claim.

## Identity

- Recovery foundation: `f2d06396268af9ba560f839a82012aa693fe60c0`.
- Numerical/integration source: `383257a05390260a5bb048b691dd3a5b3a3fb7a9`.
- Branch: `codex/research-terminal`; stacked draft PR [#6](https://github.com/SiriZhao/meridian-alpha/pull/6), base `codex/live-session-integrity`.
- Quant engine: `e510e84d05b227e2ed2333ff886d4906ecd7a80ac4e5b925c964e91567df821c`.
- Python 3.12.10; project editable import verified in the Quant worktree.
- Independent clone uses its own editable source/environment and the checked-in frozen lock; clone created at `0cc400a`, then fast-forwarded to the repaired source.
- `uv.lock`: `a9cbff33041549de7bd64db442bda108e342b03fb91858e7ea21b154256f5abc`; uv bootstrap pinned to CI's 0.12.7.
- Numerical Quant modules, Quant/risk policies, orders, daily closure and frozen original experiments have no Mission 4 diff. Native explanation validation is intentionally stricter; canonical numerical V1 default remains unchanged.

## Validation

At the frozen numerical/integration source `383257a`:

| Check | Actual result |
|---|---|
| Approved Windows host, source | 1,035 passed in 208.85s; every `validate_repo.py` stage PASS |
| Independent frozen environment/clone | 1,035 passed in 211.68s; every `validate_repo.py` stage PASS |
| Windows CI | 1,035 passed in 266.66s |
| Ubuntu CI | 1,033 passed, 2 platform skips in 272.25s |
| CI manual authority / replay | 21 / 8 passed on each OS; packaging, Skill and credential-pattern checks PASS |
| Typed artifact/frozen registry contracts | Both original Quant archives and new terminal schemas/workflows PASS |

Both [push CI](https://github.com/SiriZhao/meridian-alpha/actions/runs/37823722805)
and [PR CI](https://github.com/SiriZhao/meridian-alpha/actions/runs/37823731074)
completed successfully on that SHA. Subsequent delivery changes are documentation
only; their Git identity and CI are verified separately, not mixed into a new
financial experiment.

Statuses: **ENGINEERING_COMPLETE** for the declared bounded integration scope;
**SYNTHETIC_VALIDATION_COMPLETE**; **REAL_FINANCIAL_VALIDATION_PENDING**;
**ALPHA_NOT_YET_DEMONSTRATED**. Actual external GPT/live provider acceptance is
**NOT_RUN** in this mission.

Ignored local evidence paths include `.tmp/mission4-approved-validation-383257a.log`,
the independent clone's `.tmp/clone-approved-validation-383257a.log`,
`.tmp/mission4-final-identity.json` and `.tmp/mission4-wal-before.json`.
Only sanitized counts, identity and acceptance summaries are committed.

The restricted sandbox source/clone runs at `383257a` each reported
`1 failed, 1034 passed`, at 281.74s / 284.46s. Failure was the existing child-tree
termination test, which took about 60s. The unchanged test on approved host
passed in 1.87s. These failed attempts are retained, not relabelled as passing.
No assertion, child-process timeout or security gate was relaxed.

Before journal repair, source and independent frozen clone at `0cc400a` passed
1,030 tests and every validation stage (224.46s / 243.59s). Late WAL inspection
then reproduced coordination-file writes despite SQLite mode=ro. The repaired
shared reader refuses journal review before SQL without copying/checkpointing
the account or using immutable reads. Sixty-six targeted regression tests,
Ruff and Pyright passed after that repair.

Skill package validation: 12 files; versioned workflow contract v2, thirteen
workflows. Existing compatibility archive filename remains v1.

## Actual demonstrated behavior

- Typed bounded MCP `quant_research_snapshot` executes the existing V2.2 packet engine; factor/rank/regime/target/lineage are available without a model.
- `portfolio_what_if` takes a sanctioned private in-memory paper snapshot, distinguishes preferred/feasible weights and cost/constraint diagnostics, and applies the existing hard RiskEngine. It creates no orders, fills or ledger entries.
- `research_evidence_trace` binds exact IDs to the request/cutoff/hashes, rejecting replayed evidence.
- `review_terminal` joins compact numerical evidence into the existing shared four-role native chain. Fake-runtime integration verifies actual numerical payloads, bounded schema handling, fabricated evidence/value refusal, disagreement and rate-limit degradation.
- `generate_decision_brief` separates facts, deterministic analysis, GPT interpretation, conditional forecasts, constraints, unknowns and possible action. Prices require individual provenance and freshness; unsupported probabilities/actions remain null.
- CLI `meridian terminal` renders seven Chinese views or structured JSON before any application/ledger initialization. The sealed archive example is explicitly SYNTHETIC_DIAGNOSTIC, not current market data.
- Quant memoization binds input/cutoff/engine/challenger policy/hard risk policy, bounded TTL and capacity. Account/model conclusions are not cached. Shared model timing/token telemetry is deduplicated; unknown monetary cost remains null.
- Read-only MCP paths suppress cache/health/directory/probe writes. SQLite journal refusal is explicit. OS permissions still govern concurrent journal-mode reconfiguration; annotations and application checks are not an OS sandbox.

## Evidence and limitations

The fixture-only numerical benchmark at `0cc400a` observed approximately 140ms
for a first calculation and 15ms for a memoized repeat, with 1/0 calculations.
It used no provider/model and has unknown monetary cost/token usage. It is not
a live latency SLO, stable performance benchmark or financial evaluation.

No actual provider observation, external native GPT acceptance, canonical
Doctor/paper run or real broker call was performed in Mission 4. The canonical
runtime/database/cache/ledger were not accessed or mutated. Existing safe paper
acceptance is isolated synthetic regression, not a canonical paper day.

| Blocker | Recovery |
|---|---|
| REAL_FINANCIAL_VALIDATION_PENDING | Supply genuinely qualified adjusted PIT history and independent predeclared financial evaluation; caller certification alone is not authentication |
| EXPECTED_RETURN_UNCALIBRATED | Independently calibrate a declared estimator with qualified train/validation/OOS data |
| EXTERNAL_OPERATOR_ACTION_REQUIRED | Follow Mission 3's approved normal-terminal GPT harness with sanitized genuine evidence and matching cutoff/code identity |
| ETF/correlation/fundamental inputs unknown | Supply reliable dated look-through, aligned return history and PIT filing/revision contracts; do not guess |
| GPT review efficiency/cost benefit unknown | Compare sealed Quant-only vs Quant+GPT briefs under an independently measured review protocol |
| General concurrent autonomous orchestration PARTIAL | Current fixed planner and receipt reuse are bounded; provider acquisition remains the existing adapter workflow, not a new recursive tool executor |

No new OOS financial sample or controlled GPT benefit experiment was consumed.
Financial alpha remains ALPHA_NOT_YET_DEMONSTRATED. Revert the reviewed Mission 4
development commits for rollback; no strategy switch, reset or ledger migration
is needed. Exact recovery state is in CHECKPOINT.json and operator commands are
in OPERATOR_GUIDE.md.
