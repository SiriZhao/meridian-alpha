---
name: meridian-alpha
description: Run Meridian's authoritative Schwab-Paper daily portfolio workflow through the installed canonical CLI, inspect its persistent account, and present paper-only results without broker execution.
---

# Meridian Schwab-Paper operation

For the user request **“运行今天的 Meridian”**, immediately run the single
canonical paper workflow. Do not ask for an account name, snapshot file, cash,
market fixture, report path, provider or Python path.

```powershell
scripts/run_meridian.ps1 paper run --account Schwab-Paper --json
```

The command initializes `Schwab-Paper` to USD 100,000.00 only once. It loads the
persistent SQLite paper ledger, exports a fresh internal `PAPER_LEDGER` envelope,
then invokes the existing canonical daily path for preflight, live public market
retrieval, structured advisory research, deterministic decision/gates, eligible
paper fills, accounting, persistence and reports. It never resets the account,
uses a fixture, infers cash/positions/fills, or runs a shadow daily pipeline.

Read the JSON result before responding. Report only these concise operator facts:
status, NAV, cash, position count, daily/since-inception return if present,
benchmark/excess return if present, research status, decision status,
`paper_execution.status`, `forward_evidence.status` and maturity/sample status, blockers, and
`output_files.paper_report_markdown`.
A `PAPER_BLOCKED` result is a normal honest outcome: state the exact blocker and
next action. Do not treat runtime completion, public quotes, advisory research,
recommendation readiness, paper execution or manual authority as equivalent.

Public inputs remain `PUBLIC_RESEARCH_QUOTE`; they never become certified
execution quotes. `PAPER_EXECUTION_ONLY` never grants a manual recommendation
certificate. Broker submission is disabled. Never read, print, log or write a
credential, raw account identifier or raw snapshot.

For inspection requests, use the matching read-only canonical command:

```powershell
scripts/run_meridian.ps1 paper status --account Schwab-Paper --json
scripts/run_meridian.ps1 paper history --account Schwab-Paper --json
scripts/run_meridian.ps1 paper trades --account Schwab-Paper --json
```

Do not run `paper reset` during normal operation. It is a destructive explicit
operator action requiring `--confirm-reset Schwab-Paper`; ordinary daily use and
this Skill must never invoke it.

The original real-Host acceptance workflow remains separate. Only when the user
explicitly requests real Host analysis, require a newly supplied authorized
sanitized `HostAccountSnapshotEnvelope` and use `daily --snapshot <absolute-file>
--json`. A paper ledger must never be presented as a real broker account.