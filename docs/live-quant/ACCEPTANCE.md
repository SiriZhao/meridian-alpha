# Mission 2 — Quant-to-live bridge acceptance

Research readiness is **PREOPEN_DEGRADED**. The bridge is implemented and tested;
actual regular-session acceptance and model inference remain pending. Mission 1
remains ENGINEERING_COMPLETE / SYNTHETIC_VALIDATION_COMPLETE /
REAL_FINANCIAL_VALIDATION_PENDING / ALPHA_NOT_YET_DEMONSTRATED.

## Delivery and environment

- Development branch: `codex/quant-live-bridge`, stacked draft [PR #4](https://github.com/SiriZhao/meridian-alpha/pull/4), base `codex/quant-engine-v2`.
- Parent: `69eb57aa0f8464b18c98c9464b1c1d52a267c960`; bridge commits `29fe878`, `6bb42c7`, final implementation `3c7aa247a024608b12765ec62470048f30b31882`; actual-adapter citation correction `3c7aa24`.
- Active checkout: `E:/CSDIY/Vibe Coding Project/meridian-alpha/.worktrees/quant-engine-v2`; package imports from its `src/meridian`.
- Python: that checkout's `.venv/Scripts/python.exe`, 3.12.10. The original environment had 18 version differences; repaired with uv 0.12.7 `sync --frozen --group dev`. All 48 locked installed distributions match, plus bootstrap pip; no lock change.
- Loaded policies: active checkout's `policies`; canonical `quant-v2.1` / QUANT_V1_BASELINE, challenger `quant-v22.yaml` / SHADOW_ONLY, research `codex_cli / gpt-5.6-luna / low`. This is the application's configured model, not an assertion about the supervising agent's model.
- Runtime/cache/ledger: `E:/MeridianAlphaRuntime`, `E:/MeridianAlphaRuntime/cache`, `E:/MeridianAlphaRuntime/db/meridian.sqlite3`.
- Actual entry point: the active checkout's `scripts/run_live_advisory.ps1`, routing to `python -m meridian live-readiness` or `live-advisory`. It explicitly rejects wrong Python/import origin, including optimized Python execution.

## Engineering evidence

| Check | Result |
|---|---|
| Final local full validate_repo, implementation 3c7aa24 | 992 passed in 224.35s; dependency integrity, Ruff, Pyright, both artifact/archive contracts, CLI and optimized safe paper acceptance PASS |
| New bridge and existing live recovery regression | 64 passed in 11.43s including the native runtime; stale benchmark, future information, attribution, score overwrite, immutable records, read-only state and process-tree timeout included |
| Independent final clone | 992 passed in 214.04s at 3c7aa24; independent Python 3.12.10 import origin and frozen dependencies verified |
| Source Windows/Linux CI | [Run 37794420438](https://github.com/SiriZhao/meridian-alpha/actions/runs/37794420438) PASS: Windows 992 in 272.81s; Linux 990 + 2 platform skips in 200.98s; manual authority 21 and replay integrity 8 pass on both |
| Frozen resumed V2.2 registry | Independent clone at 6bb42c7: summary and all 76 archived replay payloads exactly match; protected engine unchanged at 3c7aa24 |
| Chinese fixture report | Independently regenerated JSON fields and Markdown exactly match committed fixture; SYNTHETIC_DIAGNOSTIC_FIXTURE_ONLY, no network/model/ledger |

Initial frozen full run passed 990 tests in 221.17s; intermediate source 6bb42c7
passed 990 locally in 207.33s and independently in 213.95s. Those are historical
checks, not the final count. A sandbox timeout-tree test failed because it could
not terminate its process tree within the unchanged 10-second assertion; the
approved host passed it. No safety constraint or timeout assertion was relaxed.

The canonical quant modules/policies, risk, orders and daily_closure are unchanged.
Engine hash remains `e510e84d05b227e2ed2333ff886d4906ecd7a80ac4e5b925c964e91567df821c`.
No registry was overwritten, refitted or consumed as new financial OOS evidence.

## Real Windows host observations

1. **09:19 New York / 13:19 UTC**, October 8: real PREOPEN_DEGRADED observation, Doctor PASS, account ready, login READY, Yahoo stale and Nasdaq fresh public reference. The development source was dirty and explicitly recorded. First immutable paths:
   `E:/MeridianAlphaRuntime/reports/live-readiness/2026-10-08/preopen-readiness.json` and `.md`; unique run `check-1322bb50cdcc4e60811bb5ee8dd67f1b`.
2. **10:15 New York / 14:15 UTC**: clean source 6bb42c7, POSTOPEN_READINESS. Doctor/account/report directory/provider/locking checks passed, model login READY; quotes remain UNCERTIFIED and history INSUFFICIENT_VERIFIED_HISTORY. Unique observation `check-0b472e7a93914ffbabff032705100fd2` beneath the same dated directory. It does not overwrite preopen evidence.
3. **10:16 New York / 14:16 UTC**: actual research run `live-036a670023724cbda985d495ac33e508`, DEGRADED, `RESEARCH_BLOCKED_DATA`. AAPL/MSFT/NVDA Nasdaq observations were 31.16 seconds old; SPY was 91.16 seconds old and failed the 90-second freshness gate. All four model stages were NOT_RUN. Login READY is not inference validation. Quant packet/comparison plus four Chinese evidence/gap rows were sealed despite the blocked model.

Actual research reports: `E:/MeridianAlphaRuntime/reports/2026-10-08/live-036a670023724cbda985d495ac33e508/live-report.json` and `live-report.md`.
The first run exposed an inaccurate GPT FAILED summary label for NOT_RUN stages.
Commit 219918a corrects this to BLOCKED_DATA and adds an explicit
model_inference_attempted flag plus stale-benchmark integration regression. The
original immutable report is preserved; it is not silently relabeled or treated
as a fresh observation from later code. No second model call was forced.

Automatic approval initially rejected the combined inference command because its
account payload and destination had not been verified. Inspection established
the destination as the existing ephemeral read-only Codex/OpenAI route and the
actual account as an internal paper ledger with empty positions and zero
exposure. No real holdings, account numbers, cash or NAV were in its portfolio
prompt. The reviewed standalone command was approved; its data gate prevented
any model inference. No rejection was bypassed.

## State and authority

The existing Schwab-Paper account, inception September 16, schema 3, ledger
version 0, was inspected read-only. Its cash/book NAV was 100000 with no positions;
the latest dated mark and canonical ownership were October 7 PAPER_NO_TRADE.
Book NAV is not a fresh broker NAV and a local read timestamp is not a broker
confirmation. Pending/partial broker state and sector metadata remain unknown.

Canonical DB SHA256 before and after both host observations is identical:
`88d2872f0f263370e11b7fe5712d7b1c644de7e685c9d594429015f5fb619a55`.
Schema fingerprint and all table counts are identical: zero paper fills/positions,
two existing daily ownership rows. Doctor/report/cache/lock probes used approved
host access; no canonical ledger migration, reset, account initialization, daily
paper execution, order or broker side effect occurred. HSBC was not accessed.

## What reaches the live path

Existing V2.2 features, six-factor attribution, rank/eligibility, regime, risk and
preferred/feasible/cost-adjusted targets enter both native research and final GPT
interpretation under quote/history hashes and a shared cutoff. Integration tests
prove qualified fixture fields arrive and model mutation cannot change stored
scores. That fixture is not genuine financial evidence.

Actual public history cannot prove split/action-adjusted cross-session returns.
Its provisional lane therefore exposes only safe completed-session diagnostics;
strict momentum/trend/relative strength/volatility/rank/entry zones remain absent
with explicit reasons. Missing benchmark and stale current prices are never
converted to zero or optimistic ranks. No fabricated catalysts, fair values,
expected returns, calibrated profit probabilities or attractive prices appear.

Three provenances remain separate: V1 canonical NOT_RUN_BY_LIVE_ADVISORY, V2.2
SHADOW_ONLY research, GPT ADVISORY_ONLY interpretation. No authorized trade output
is produced. Model failures and missing evidence retain the deterministic record.

## Operator next step and limitations

Follow [LAUNCH_GUIDE.md](LAUNCH_GUIDE.md) and the updated daily operator runbook,
using this exact checkout and approved host launcher. See
[RISK_REGISTER.md](RISK_REGISTER.md), [ACCEPTANCE_PROOF.json](ACCEPTANCE_PROOF.json)
and [CHECKPOINT.json](CHECKPOINT.json). The fixture sample is explicitly historical
synthetic regression, never today's live report.

Next real acceptance action: obtain a fresh source-bound benchmark and complete
watchlist observation, genuine action-qualified/PIT history, and the separately
required fresh account evidence; run the same bounded workflow and inspect its
saved record before any independent second qualifying cycle. Missing certification
may correctly yield WAIT_FOR_EVIDENCE. Do not weaken freshness gates, force a time,
create an account, reset a ledger or run paper trades to show activity.

Model inference, two-cycle regular-session acceptance, certified execution quotes,
real financial validation and alpha remain unproven. V1/parent checkout is the
rollback path and needs no ledger change. Final documentation commit/remote SHA
and its CI are verified externally after publication; this record identifies the
accepted implementation source without a self-referential commit hash.

Final actual-adapter audit caught a missing citation catalog entry: the final GPT
output schema admitted quote IDs but omitted its separately supplied Quant IDs.
Commit 3c7aa24 includes both in the strict catalog; the regression inspects the
actual adapter-generated schema and validates a complete cited response, while
invented IDs and additional fields remain forbidden. This is fixture-only adapter
validation, not a successful real model call. The 219918a full checks (991 local
and independent tests) are historical; the table above reports the final source.
