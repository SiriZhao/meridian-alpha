# Meridian operational data audit — 2026-09-02

## Baseline

- Starting commit: `c5fd871`.
- Preserved user-owned worktree change:
  `reports/gate6g-quote-preflight.json`.
- Runtime doctor uses Python 3.12.14 from `.venv`; a newly initialized runtime
  database remains correctly `PENDING`, not silently redirected.

## Implemented

- Added an explicit operational data plane with project-owned normalized quote,
  provider result, immutable refresh snapshot, shared freshness policy, health
  states, discrepancy gate, and provenance/content hashes.
- Operational readiness is independent from research/PIT: a fresh public quote
  can be `OPERATIONAL_READY` while research remains `RESEARCH_BLOCKED`. It is
  never `CERTIFIED` and cannot authorize manual entry.
- Added atomic cache writes. Corrupt cache files are quarantined with a
  `.corrupt` suffix and ignored; they cannot crash the refresh path or become
  fresh data.
- Added additive `data-status --json` support through the Windows launcher.

## Real bounded provider smoke

One AAPL request per provider, 4-second timeout, 2026-09-02:

| Provider | Result | Interpretation |
| --- | --- | --- |
| Yahoo chart public | Returned last `325.13`, timestamp `2026-09-01T20:00:01+00:00` | Operational/public-shadow only; not PIT or execution certified. |
| Stooq public | HTTP 404 translated by its existing adapter to `QuoteProviderError` | Unavailable/degraded; no fallback data was invented. |

## Coverage and blockers

- Today: bounded normalized operational quote collection, cache and
  freshness/conflict diagnostics can work once wired to the daily application.
- Still blocked: certified research/PIT, historical universe certification,
  execution quote certification, real Host account input, and all broker work.
- Existing CLI/MCP/daily wiring remains a follow-up because current session ACL
  restrictions prevent safely editing pre-existing source files. The additive
  module/launcher is tested but does not claim that `meridian daily` consumes
  operational snapshots yet.
