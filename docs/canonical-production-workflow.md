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
