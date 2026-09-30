# Canonical production workflow

## Authoritative path

```text
CLI / PowerShell launcher / Skill / MCP Host-envelope tool
→ MeridianApplicationService
→ init + doctor + snapshot validation
→ OperationalMarketSnapshotService
→ CanonicalResearchStage
→ DailyClosureService
→ readiness and seven gates
→ AuditStore + canonical JSON/Markdown
→ optional paper-only ledger sink
→ Forward Evidence Factory
```

`MeridianApplicationService.daily` is the only Host/paper daily execution path.
`paper run` creates a temporary `PAPER_LEDGER` envelope and calls it; it does not
fetch or decide independently. CLI and the launcher delegate to the same
application façade. The Skill calls `paper run` for Schwab-Paper. The MCP Host
envelope tool now writes only a short-lived sanitized file and delegates to the
same method. The old MCP `AccountSnapshot` daily tool returns
`CANONICAL_HOST_ENVELOPE_REQUIRED` rather than creating a parallel decision.

Renderers only display the returned report and never calculate trades.
`DailyClosureService` remains the deterministic closure. Research is advisory,
public quotes are operational only, and manual/broker authority stays blocked
unless the existing sealed gates separately prove it.

## Codex-to-host execution contract

The application path above does not define the operating-system execution
boundary. For Codex-triggered canonical writes, the complete path is:

```text
user daily intent
→ Codex project/Skill routing
→ approved host execution
→ host PowerShell
→ scripts/run_meridian.ps1
→ project .venv Python
→ E:\MeridianAlphaRuntime
```

The four relevant layers have separate responsibilities:

- The repository launcher selects the checkout, `.venv` Python, and configured
  runtime. It cannot elevate a restricted Codex process.
- The MCP server exposes Meridian tools and delegates application operations.
  It is not a host bridge and must not be used to impersonate one.
- `AGENTS.md` and the Meridian Skill classify canonical writes and require host
  approval before invocation.
- The Codex product approval/execution facility establishes the actual host
  boundary. Repository code cannot grant or bypass that approval.

Canonical writes include paper/canonical runs, ledger mutation, report and
cache writes, migrations, runtime write probes, and the write-probe portions of
`doctor`. Codex must request approved host execution before running them; it
must not use a failed sandbox attempt as the trigger for escalation.

If approval is pending, no canonical command runs and the conversational status
is `HOST_APPROVAL_REQUIRED`. If host execution is rejected, unavailable,
capacity-limited, or cannot enter the host context, no sandbox fallback occurs
and the status is `HOST_EXECUTION_UNAVAILABLE`. These are execution-routing
states, not database health findings. A real storage diagnostic is reported
only when the command actually ran in an approved host context.

For “运行今日 Meridian Alpha” and equivalent requests, Codex verifies the repo,
`.venv`, canonical runtime/account and current date; obtains host approval;
runs host-approved `doctor --json`; and only after `PASS` runs host-approved
`paper run --account Schwab-Paper --json`. It then reports the canonical result
fields and verifies the runtime root, same-day idempotency, and absence of any
broker side effect. Calendar policy chooses the trading date. Operators and
tests must not force or recreate historical paper days.

Before creating a paper snapshot, `paper run` resolves the current New York
trading date and performs an authoritative ledger idempotency read. If a
committed `PAPER_COMPLETE` or `PAPER_NO_TRADE` row already owns that account and
date, the attempt emits `PAPER_ALREADY_EXECUTED` and skips market retrieval,
research, decision, and paper-order stages. The report records the attempted
run, authoritative existing run, `SKIPPED` stage statuses, and zero side
effects. This read is only a cost optimization; the transactional check inside
`PaperLedger.execute` remains the final race-safe guard. Failed or blocked
markers do not own a date and can be retried.

Canonical stage lifecycle values are `SUCCESS`, `FAILED`, `DEGRADED`,
`BLOCKED`, `NOT_RUN`, `SKIPPED`, and `INHERITED`. `SKIPPED` means the current
workflow intentionally did not run a stage and includes a reason. `INHERITED`
is reserved for content copied from an authoritative run and must include its
`source_run_id`; duplicate paper runs use `SKIPPED` because they do not copy
research or forward-evidence content. Duplicate attempts never freeze a second
forward-evidence observation.

## Runtime contract

`RuntimePaths` is the single mutable-root contract. Windows defaults to
`%LOCALAPPDATA%\MeridianAlpha`; an absolute writable `MERIDIAN_HOME` is the only
override. `init` is idempotent and migration-safe; `doctor` reports pending,
current, degraded or failed storage without creating a fallback database.
The launcher always selects the project `.venv` Python. Reports, cache, audit,
logs and SQLite remain under the runtime root.

## Operator status

The daily report begins with runtime/analysis, freshness, research/decision and
forward-evidence maturity. A `PAPER_BLOCKED` run is successful fail-closed
operation when a regular-session fresh market or validated advisory research is
missing. It never means a fill, manual authority, certified quote, or real
broker account.
