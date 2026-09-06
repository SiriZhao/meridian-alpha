# Reliability Reset baseline — 2026-09-07

Source of truth: installed metadata points to `meridian.application_cli:main`
in this checkout. Starting branch `main`, commit `7264d7531862bb71703866899fa71cf3a6c3671c`.
Preserved user modification: `reports/gate6g-quote-preflight.json`.
Maintenance branch: `astra/reliability-reset`.

Observed before changes, on Windows / PowerShell:

| Component / command | Result | Evidence |
| --- | --- | --- |
| Sandbox process creation | FAIL | `helper_unknown_error: apply deny-read ACLs`; approved external process execution works |
| `uv run meridian doctor --json` | FAIL | uv not on PATH |
| `.venv/Scripts/python.exe` | PASS | Python 3.12.14 |
| `.venv/Scripts/meridian.exe doctor --json` | DEGRADED | LocalAppData directories writable, timezone/config/dependencies pass; DB missing, migration PENDING |
| documented `daily --profile TEST` | FAIL | canonical parser rejects --profile |
| Daily pipeline / reports / live providers | UNKNOWN | not yet executed |
| LLM research | UNKNOWN | canonical daily does not invoke research; presence of adapter code is not provider availability |

The launcher and installed/repository Skill still describe older CLI contracts.
No real account snapshot or credentials have been read. No production success
is inferred from fixture runs or existing historical reports.


## Repairs and observed evidence

- Entry drift: README profile command rejected before repair. Launcher and both
  repository/installed Skill now use canonical CLI. Windows PowerShell 5, outside
  checkout, fixture daily: exit 0, DRAFT / RESEARCH_ONLY, valid JSON/Markdown/log.
- Missing DB: daily now uses existing init/migration and AuditStore. Subprocess
  E2E uses fresh Chinese/space/# paths, runs twice, preserves both records and
  verifies integrity. Newer schema is rejected and user table preserved.
- SQLite connections now close explicitly. Windows rename-after-init/doctor
  regression passes; URI escaping handles # and spaces.
- CWD config dependency: wheel includes policies. Actual built wheel extracted
  into a temporary installation, outside checkout: init 0, doctor PASS, policies
  resolved inside the installed wheel resources.
- Live-time bug: Yahoo direct quote request PASS but old pipeline reported
  INVALID_RESPONSE because received_at exceeded pre-request cutoff. Explicit
  live cutoff now closes after reception. Fixed replay rejection still passes.
- Real public-provider daily with synthetic account: exit 2,
  BLOCKED_STALE_MARKET, Yahoo STALE for AAPL/MSFT/NVDA/SPY, Stooq UNAVAILABLE.
  JSON/Markdown/log and DB persisted; measured daily service time 6.406 s.
  Evidence: temporary `meridian-reality-wm7_58hd/runtime`, run
  `daily-6203735073646a286cfa7996`. This is NOT real-account acceptance.
- Error probes: path occupied by file, relative MERIDIAN_HOME, missing snapshot
  all return exit 3 with structured actionable diagnostics, no traceback.
- Actual process check: process_is_admin=False. The Codex sandbox helper remains
  unavailable, so tool processes used approved outside-sandbox execution under
  the same ordinary Windows user; this did not require Windows elevation.
- uv exact sync unexpectedly removed optional packages. Restored all 84 recorded
  versions, compared metadata with zero mismatches; pip check PASS. Use inexact
  sync for maintenance. The regenerated lock includes previously declared
  optional dependency graph as well as explicit Windows tzdata.
- Optional dependencies exposed a scripts namespace collision in pytest's
  executable invocation. Explicit project scripts package/pythonpath fixes it.

Final checks: `uv run --no-sync pytest -q`: **304 passed, 14.66 s**;
`uv run --no-sync ruff check .`: **PASS**; `uv run --no-sync pyright`:
**0 errors, 0 warnings**. Used the project's `.venv/Scripts/uv.exe`; no-sync
keeps the restored optional environment intact.

## Acceptance limits

R1–R4, R6, R8–R10, R13–R15 verified for the bounded fixture workflow.
R5: runtime writes and wheel policy discovery verified outside checkout; a
full daily under a genuinely read-only installation ACL remains unverified.
R11/R12: terminal launcher preserves exits; common input/path failures verified.
Exhaustive ACL/long-path/provider/LLM failure coverage is not claimed.
R7 is DEGRADED: no new real Host snapshot, current public quotes stale, secondary
unavailable. Canonical LLM research remains NOT_RUN, not a credential diagnosis.
The full certified research-to-decision workflow has NOT been accepted.
Reliability Reset remains DEGRADED; Controlled Improvement has not started.
