# Controlled Improvement Phase 1 — Batch 3 acceptance

**Production acceptance: BLOCKED.** Engineering/regression acceptance is verified
within the scopes below. Phase 1 cannot be closed as production-like accepted;
Phase 2 strategy work should not begin. Architecture and investment authority stayed
frozen; no broker APIs, execution, model changes or optimizer changes were added.

## Environment and baseline

Windows 11 (10.0.26200), Python 3.12.10, PowerShell 5.1.26100.9278.
Branch `astra/controlled-improvement-batch3`; start `b92a314`, ending implementation
`30e5a33`. Commits `935433a` (failure handling/operator tests) and `30e5a33`
(acceptance collector). The following documentation commit records the evidence.

The resumed checkout already had Batch 3 drafts and historical evidence. A stalled
execution channel recovered; no running test processes were observed. `.venv` was
missing, while system Python was 3.14. Existing Python 3.12 was used to restore a
new local environment with `uv sync --inexact --group dev`; no exact sync or deletion
of an existing environment. User report hash matches the checkpoint exactly.

First executable baseline: 367 passed / 7 failed. Six failures came from an unfinished
test importing the wrong Stooq class; one was a mocked graph-routing test depending
on optional TradingAgents being installed. Tests now inject that dependency condition
explicitly; real adapter availability checks remain unchanged. No failed tests removed.

Final: **375 passed (38.36 s)**, Ruff PASS, Pyright zero errors/warnings. Both dev
and installed-wheel `pip check` passed. Wheel installation used its declared dependency
ranges; dev used the lockfile. All wheel Python sources match the final source tree.
See [check output](evidence/batch3/checks-resume.json).

## Bugs reproduced and repaired

- Report write failure formerly lost the original identity at the outer CLI handler.
  It now returns MERIDIAN_REPORT_WRITE_FAILED with the original run_id, usable log,
  explicit partial artifacts and next actions, and appends a linked failure receipt
  where SQLite is available. The failure is logged; existing evidence is preserved.
- Missing launcher Python now returns structured JSON for --json, exit 3 and a
  recovery action. Plain terminal diagnostics remain supported; no pause added.
- Operator report now exposes account/market freshness, actual research invocation,
  decision completion and readiness in its first screen, with gates and next actions.
- The interrupted acceptance script's outside directory was actually beneath the
  checkout. Resumed evidence uses a real OS temporary directory outside the checkout.

## Runtime, DB, installation and E2E

A freshly rebuilt wheel was installed in an isolated Python environment. Its actual
meridian.exe resolved package policies from site-packages without policy overrides.
Init, doctor, missing-snapshot daily, synthetic daily, PowerShell 5 launcher daily,
restart doctor and public provider probes executed. Daily exits were 2/0/0, with
run IDs, JSON/Markdown/log output paths and next actions. All synthetic account runs
are **REGRESSION_ONLY**, never real account acceptance.

Three run/readiness records survived restart; integrity_check was ok and the DB was
renamed and restored without leaked Windows handles. Tests also cover locked/newer
DBs, migration rollback and preserved historical records. A temporary deny-write ACL
on the isolated install was tested and restored in finally; writable runtime still
initialized and produced reports. The final wheel was rebuilt after a headline-only
report edit; final outside-cwd E2E and source equality were checked independently.

[Latest run IDs, paths, provider payloads](evidence/batch3/runtime-resume.json) ·
[Read-only install](evidence/batch3/readonly-resume.json). Earlier interrupted and
initial-resume evidence is retained separately, not relabeled as current production.

## Account, market, research and decision

No explicitly supplied new real sanitized Host snapshot was found. Located candidates
were examples/templates or historical reports. Real account status is
**BLOCKED_MISSING_REAL_HOST_SNAPSHOT**. No positions, cash or fills were inferred.

Actual Yahoo/Stooq requests covered AAPL, MSFT, NVDA and SPY. Yahoo was STALE;
Stooq was UNAVAILABLE (HTTP 404 in recorded probes). CLOSED-session quotes refer to
the prior completed session; this is not treated as a freshness bug. No standards
were relaxed. Timestamps, receipt/attempt/finish, ages and per-lane latency are in the
machine report; unavailable observations retain null source/receipt fields.

LLM configuration reference is CONFIGURED_UNPROBED, **not NOT_CONFIGURED or
AUTH_FAILED**. Actual canonical invocation is false / NOT_RUN because fresh real
upstream inputs are absent. No direct adapter call was used to bypass that boundary.
Configured fixture requests verify daily → schema validation → decision context →
gates → reports → SQLite, including authentication/timeout/malformed/schema failure.
They establish implementation behavior, not live availability. Public advisory output
cannot certify execution or issue sealed manual authority.

## Acceptance matrix

| Item | Status | Verified scope / missing evidence |
| --- | --- | --- |
| R5_runtime_paths | **VERIFIED** | Wheel resources and writable runtime; actual cwd outside checkout; temporary install ACL deny restored |
| R7_real_daily | **BLOCKED** | No fresh explicitly supplied real Host envelope; market stale; canonical live research not executed |
| R11_R12_operator_failures | **VERIFIED** | CLI failures are structured with run_id/next_actions; missing Python exits 3; report failure retains identity |
| real_host | **BLOCKED** | BLOCKED_MISSING_REAL_HOST_SNAPSHOT; only examples/templates/historical reports located |
| synthetic_account_boundaries | **VERIFIED** | REGRESSION_ONLY: fresh/missing/malformed/stale/future, replay and privacy |
| actual_public_requests | **VERIFIED** | Actual Yahoo/Stooq requests for AAPL/MSFT/NVDA/SPY; availability is not inferred |
| closed_market_behavior | **VERIFIED** | Observed CLOSED session; old closing quote stays STALE without lowering thresholds |
| fresh_open_market | **NOT_TESTED** | Actual requests occurred during closed session; no fresh open-session acceptance |
| acceptable_live_freshness | **BLOCKED** | Yahoo STALE, Stooq UNAVAILABLE; no quote selected |
| provider_faults_and_fallback | **VERIFIED** | REGRESSION_ONLY: timeout, DNS/OSError, invalid payload, primary/secondary selection and both unavailable |
| actual_rate_limit | **NOT_TESTED** | No actual rate-limit acceptance; no provider stress requests made |
| llm_failure_coverage | **VERIFIED** | REGRESSION_ONLY canonical CLI: missing config/auth/timeout/malformed/schema failure; existing 429/retry tests |
| live_canonical_research | **BLOCKED** | CONFIGURED_UNPROBED; actual invocation false; real upstream account absent |
| full_research_to_decision | **DEGRADED** | Canonical fixture schema/context/gates/report/SQLite verified; real transition not accepted |
| authority_separation | **VERIFIED** | REGRESSION_ONLY all-prerequisite model and sealed gate tests; DRAFT/public quotes do not authorize manual entry |
| quote_certification | **BLOCKED** | No certified execution quote; all public observations uncertified |
| windows_launcher_installation | **VERIFIED** | PowerShell 5.1, Chinese/space/# outside cwd, actual wheel entrypoint, init/doctor/daily/restart |
| db_durability | **VERIFIED** | Fresh/existing/failed run/restart, 3 audit rows, integrity ok, actual rename; locked/newer schema/migration rollback regression |
| report_and_skill | **VERIFIED** | JSON/Markdown/logs; headline status checked; repository and installed Skill SHA256 identical; parser/launcher options aligned |
| regression_and_dependencies | **VERIFIED** | 375 tests; Ruff/Pyright; dev and installed-wheel pip check; wheel source matches checkout |

Each VERIFIED row has an explicit test/evidence reference in the
[machine acceptance report](../reports/controlled-improvement-phase1-acceptance.json).
Negative coverage includes missing/invalid/stale/future snapshot, problematic runtime
path, newer/locked DB, quote timeout/DNS/invalid/stale/secondary unavailable, LLM
missing configuration/auth/timeout/malformed/schema failure and report write failure.
No actual rate limit was induced. Pure all-prerequisite tests establish aggregation
semantics only; current public canonical output remains research-only and BLOCKED
for manual authority.

## Operator contract and remaining limits

README, repository Skill, installed Skill and actual parser agree on doctor and
`daily --snapshot <absolute-file> --json`; --market-fixture is regression only and
--profile is unsupported. Skill hashes match; no synchronization was necessary.
Use [the operator runbook](daily-operator-runbook.md) for recovery commands.

SQLite and report files remain separate persistence boundaries. A partial JSON may
contain the prior analysis outcome; consult the returned failure and linked audit
receipt, not that partial file alone. Citation membership cannot prove model prose
true. Shared HTTP socket timeout is not a hard process deadline and response-size
validation follows transport read. These limitations are not promoted to VERIFIED.

The next three acceptance priorities are a fresh authenticated Host snapshot,
fresh open-session provider evidence, and an actual canonical live research-to-decision
run followed by existing certification review. No safe production promotion can occur
without that evidence. Stop feature work here; no automatic Phase 2 redesign.
