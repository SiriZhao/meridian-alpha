# Daily operator runbook

Follow the canonical Windows command in [README](../README.md).

For the separate Quant-to-live research workflow, use the verified
[Mission 2 active-checkout guide](live-quant/LAUNCH_GUIDE.md). Its readiness mode
and research mode share `run_live_advisory.ps1`; neither runs paper trades.
V1 stays canonical. V2.2_SHADOW and GPT_ADVISORY retain separate provenance,
public inputs remain unverified, and missing factors/prices remain UNKNOWN.

For the separate read-only Quant terminal, follow the
[Mission 4 operator guide](research-terminal/OPERATOR_GUIDE.md) from its verified
development checkout and Python environment. `meridian terminal` reads an
explicit bounded history request and prints Chinese/JSON research views; it
does not initialize accounts, invoke Doctor, fetch prices or run a paper day.
The Skill's Quant/what-if/lineage tools are research-only. Missing current prices
and account evidence stay blockers, and journal-review refusal must not be
resolved by deleting canonical SQLite coordination files.

## Forward evidence and alpha lab

The [isolated alpha lab](alpha-lab.md) is a separate read-only research workflow.
Its scoring/reconciliation commands do not initialize accounts or run a paper
day. Reviewed close imports write only isolated `alpha-lab` JSON ledgers. Do not
use canonical paper runs to create extra forward samples, reconstruct fills or
test strategies. Public quotes never become certified execution quotes through
reviewed research returns.

Read `decision_attribution` in the sealed canonical report for actual no-trade
branches. GPT completion does not establish influence on operational weights.
Legacy forward row count is separate from receipt-qualified financial samples;
missing actions/closes remain unresolved. See the
[Phase 4 checkpoint](audits/2026-10-08-phase4-checkpoint.json) for outstanding
portfolio evaluation, ablations and fresh host acceptance.

## Astra Skill research and acceptance

Use the installed `meridian-alpha` Skill for evidence-grounded research.
The Skill uses read-only MCP tools and Astra performs synthesis itself.
`research_packet` accepts a symbol and cutoff; optional news/macro evidence
must be supplied with sources. Missing inputs stay unknown. The legacy
daily-analysis tools are no longer registered with MCP; paper remains a
separate explicit CLI workflow.

For market research, use `market_snapshot` first. The active fallback sequence
is local cache, Yahoo structured data, Astra trusted-web evidence, then
UNKNOWN. When Yahoo is stale or unavailable, Astra may browse trusted sources
and call `validate_market_evidence`; Meridian never performs that browse or
starts another model. Submit a compact URL-backed scalar fact, not a snippet or
model estimate. Keep source conflicts visible. Historical indicators require a
machine-readable table, CSV, or JSON source; otherwise report
`HISTORICAL_DATA_UNAVAILABLE`. All such inputs remain research-only and
`execution_authority=NONE`.

As of the final 2026-09-11 review, local/runtime and clean-install checks pass,
but real fresh Astra acceptance is `BLOCKED_WITH_EVIDENCE / CODEX_RATE_LIMITED`.
Do not retry a quota failure in a loop. SEC HTTP 403 is a separate provider
access blocker, not missing corporate fundamentals. Last-session quotes may
be useful research context while still marked stale and execution-blocked.

Runtime PASS establishes installation health. Research AVAILABLE requires
usable evidence and completed synthesis. Neither grants manual-entry readiness.
Schwab-Paper fills are simulated; real brokerage execution is unsupported by
the Astra Skill and `execution_authority` remains `NONE`.

## Daily Schwab-Paper operation

For normal paper operation, run exactly one command:

```powershell
.\scripts\run_meridian.ps1 paper run --account Schwab-Paper --json
```

Do not create or edit an account envelope, cash balance, position file or
market fixture. The command requires an existing paper account and never
automatically initializes, resets or replaces its history. A missing account
returns `PAPER_ACCOUNT_NOT_FOUND`; inspect storage and obtain a separately
approved explicit initialization only if no account/history exists. It exports
a fresh paper-ledger observation (not a fresh broker confirmation), invokes canonical
daily and attempts paper-only fills after the same market/research/decision
checks. Inspect `output_files.paper_report_markdown` and the structured
`paper_execution` result. `PAPER_BLOCKED` is a valid, non-destructive outcome
when the market is closed, public inputs are stale or research is unavailable.

Use `paper status`, `paper history`, and `paper trades` for inspection. Never
call `paper reset` in normal operation; it requires an exact explicit
`--confirm-reset` account-name confirmation.

## External Host operation

1. Run doctor; correct FAIL diagnostics. Daily initializes a missing DB.
2. Supply a new sanitized HostAccountSnapshotEnvelope; never assume prior fills.
3. Run daily --snapshot <absolute-file> --json.
4. Read output_files and separate runtime completion from recommendation readiness.
5. Current canonical output is research-only. Read the actual research status. A DRAFT
   does not have sealed seven-gate manual authority or a certified quote.

For explicit Host research, use the prepare/result/resume lifecycle. The result
must copy the job's `job_id`, `run_id`, `market_snapshot_id` as
`research_snapshot_id`, and `as_of` as `research_as_of`, and must declare
model/runtime provenance. On resume:

- `EXACT` uses the bound snapshot;
- `REVALIDATED` records old/new references after bounded deterministic price-only reconciliation;
- `REFRESH_REQUIRED` creates a new job and does not classify market drift as an LLM failure;
- wrong IDs/snapshot, malformed output, timeout, and duplicate conflict are Host failures.

Read `status_dimensions` before the top-level status. `MARKET_CLOSED`, research
waiting, research refresh, Host failure, deterministic risk blocking, and a
paper no-fill are intentionally different outcomes.

No broker execution or automatic orders. Missing fresh account/market facts
cannot be inferred from conversation or fabricated. Use fixture input only for
explicit regression, never for a real account request.


Read `readiness` first. Runtime PASS only says the invocation completed its
operational work. Recommendation remains BLOCKED if any required dimension is
UNKNOWN, NOT_RUN, stale, unverified or incomplete. Public quotes never certify
manual execution. AVAILABLE research means validated model inference, not certification.

Use `snapshot validate <file> --json` to inspect freshness and hashed identity
without consuming input. Daily records each snapshot once across processes;
REPLAYED or ID_CONFLICT requires a new Host snapshot. Never change an ID simply
to disguise a replay. Pending/partial state blocks the decision path.

For provider failures, inspect both lanes in `provider_probes`: attempt/completion
and receipt times, observed session, cutoff, selection, cache, and final status.
During closure, LAST_COMPLETED_SESSION_ONLY is context, not a freshness override.


## Optional canonical research

Use the existing `models.yaml` research settings in the selected policy directory
(`MERIDIAN_POLICY_DIR` if configured): provider `codex_cli`. Paper runs
enable the otherwise opt-in research stage locally. Meridian invokes the local
Codex CLI and relies only on its existing ChatGPT-managed login. Do not set an
OpenAI, Codex, or DeepSeek API key for this workflow.

Optional runtime overrides are `MERIDIAN_CODEX_MODEL`,
`MERIDIAN_CODEX_REASONING_EFFORT` and
`MERIDIAN_CODEX_TIMEOUT_SECONDS`. Omit the model to inherit the Codex CLI
default. The normal reasoning default is `medium`.

The same daily command invokes the stage only after input validation. The actual
request is the provider probe. Inspect `research.context.status`, `attempts`,
`provenance`, `provider_diagnostics`, `error_code`, and `next_action`.
`CODEX_AUTH_REQUIRED` requires running `codex login` and signing in with
ChatGPT. `CODEX_RATE_LIMITED`, `CODEX_TIMEOUT`, `CODEX_PROCESS_ERROR`,
`CODEX_SCHEMA_ERROR`, `CODEX_EMPTY_RESPONSE`, and
`CODEX_OUTPUT_MISSING` remain explicit and fail closed. No automatic provider
fallback exists.
A missing snapshot prevents the stage entirely. No automatic cached research is used.
Public advisory success is AVAILABLE, while certified research/manual gates remain
unmet.

Run the single-call opt-in integration check only when needed:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_codex_provider.py
```

It consumes one Codex run, uses a minimal public fixture, validates the output
schema, and prints only provider diagnostics and hashes. It is not part of
startup, CI, or the unit suite.


## Failure recovery and acceptance

From any working directory, invoke the launcher by its absolute path:

```powershell
& "E:\CSDIY\Vibe Coding Project\meridian-alpha\scripts\run_meridian.ps1" doctor --json
& "E:\CSDIY\Vibe Coding Project\meridian-alpha\scripts\run_meridian.ps1" daily --snapshot "C:\Inputs\today.json" --json
```

`--snapshot`, `--market-fixture` (regression only), and `--json` are current parser
options; no `--profile` option exists. A process exit of 0 can still carry BLOCKED
recommendation readiness. Read the JSON before presenting a result.

If the checkout virtual environment is missing, the launcher returns
MERIDIAN_PYTHON_MISSING with exit 3 (structured for --json). Restore Python 3.12
and dependencies with `uv sync --inexact --group dev`; do not use system Python
3.14 or exact synchronization as a substitute. Doctor rechecks the restored path.

MERIDIAN_REPORT_WRITE_FAILED retains the analysis run_id and appends a linked
failure receipt where the DB remains writable. `partial_output_files` are incomplete
artifacts, not completed reports; `output_files` only lists usable diagnostic logs.
Do not trust a partial JSON reporting the earlier analysis outcome as successful
report persistence. Inspect free space, permissions and file locks, preserve audit
history, and supply a new snapshot for a subsequent daily run.

[Phase 1 acceptance](controlled-improvement-phase1-acceptance.md) distinguishes
verified regression behavior from blocked real Host/research acceptance.
## Live production acceptance

Use the bounded acceptance command during a NYSE regular session only when you have a newly exported sanitized Host envelope:

```powershell
& ".\scripts\run_production_acceptance.ps1" -Snapshot "C:\Inputs\today.json"
```

It records doctor, safe pending migration, snapshot validation, canonical market probes, policy state and—only if input and session qualify—canonical daily. When the market is closed, it writes `OPEN_SESSION_ACCEPTANCE_NOT_AVAILABLE`, does not wait, and does not call daily or LLM research. It never enables research, reads a credential, changes portfolio policy or submits an order. See [live acceptance](controlled-improvement-phase1-live-acceptance.md).


## Canonical daily and forward evidence

For the default paper workflow use only:

```powershell
.\scripts\run_meridian.ps1 paper run --account Schwab-Paper --json
```

Read `forward_evidence` from the returned JSON or run:

```powershell
.\scripts\run_meridian.ps1 forward-status --json
```

`NOT_MATURE` means the factory has insufficient mature samples. It is not a
strategy verdict and never permits automatic promotion. If a daily result is
blocked, preserve its report and correct the named account, market, research or
runtime condition; never freeze a fixture or use a second daily command.

## Startup status and degraded operation

The first screen of every canonical daily report shows Environment, Cache, Data Provider, Market Status, and Execution Mode. Treat `DATA_DEGRADED` as usable only for the stages whose individual freshness and provenance checks pass. Treat `SAFE_ANALYSIS` as analysis-only: review the account risk and portfolio checks, resolve the stated cache/provider/session blocker, and rerun. It never authorizes a real or paper fill from stale or missing data.

For `MERIDIAN_FILESYSTEM_ERROR` on a Windows cache path, run `doctor --json` and inspect the cache diagnostic. If the configured directory is EFS-encrypted and the current identity lacks its key, configure an absolute non-EFS `MERIDIAN_CACHE` path as documented in `docs/runtime.md`; do not move the database or reports as an implicit fallback.
