# Controlled Improvement Phase 1.5 — live production evidence

## Current production status

**BLOCKED.** Runtime engineering is verified, but this is not production decision-support acceptance. No order was sent, no broker integration exists, and public quotes remain non-execution-grade.

## What this run verified

- Baseline: 375 tests passed; Ruff passed; Pyright reported zero errors and warnings. The exact command results are in the live acceptance artifact.
- The canonical Windows launcher used Python 3.12.10. The current user-local SQLite database was safely upgraded from pending v1 to current v2 through canonical `meridian init`; doctor then passed. No database was cleared.
- The bounded PowerShell acceptance harness called canonical doctor and data-status, generated structured evidence, and exited normally while the market was closed. It did not call daily or an LLM.
- Batch 3 remains the evidence for wheel installation outside the checkout, PowerShell 5 compatibility, report-failure receipts, and database durability.

## Host snapshot

**NOT SUPPLIED — BLOCKED_MISSING_REAL_HOST_SNAPSHOT.** The workspace contains only templates, fixtures and historical reports. Nothing was inferred from them. [The template](../schemas/examples/real-host-envelope-template.json) is explicitly `TEMPLATE_ONLY`, `NOT_REAL_ACCOUNT`, and `NOT_ACCEPTANCE_EVIDENCE`.

When a newly exported sanitized envelope is available, first run:

```powershell
& ".\scripts\run_meridian.ps1" snapshot validate "C:\Inputs\today.json" --json
```

Validation checks schema, timestamps, freshness, pending state and snapshot identity without consuming the input. A new ID cannot disguise repeated facts.

## Market

The acceptance run occurred in scheduled `CLOSED` US-equity context, so **fresh_open_market = NOT_TESTED** and `OPEN_SESSION_ACCEPTANCE_NOT_AVAILABLE` is the correct result. Its next valid context is a NYSE regular session, 09:30–16:00 America/New_York.

The canonical probe covered AAPL, MSFT, NVDA and SPY. Yahoo returned prior session observations and each was marked `STALE`; Stooq was `UNAVAILABLE`. No freshness threshold was changed.

Stooq investigation found correct configured mappings (`aapl.us`, `msft.us`, `nvda.us`, `spy.us`). The adapter URL, the standard `i=d` URL variant, and the `.pl` hostname each returned Stooq's own HTTP 404 page for `aapl.us`. This is **UPSTREAM_UNAVAILABLE / endpoint changed**, not an adapter symbol formatting bug. Meridian therefore continues to expose secondary `UNAVAILABLE` and never promotes it to PASS.

## LLM and research-to-decision

Batch 3 recorded a configured-but-unprobed credential reference. Phase 1.5 intentionally did not inspect any credential; its machine artifact records `UNPROBED_NOT_INSPECTED`. Current policy has `research.live_enabled=false`; more importantly, no fresh real Host snapshot and no regular-session market input were available. Canonical daily was intentionally not invoked, so:

- live canonical LLM HTTP request: **not sent**;
- advisory research: **NOT_TESTED**;
- real ResearchDecisionContext → decision → gate transition: **NOT_TESTED**.

Fixture coverage remains engineering evidence only. Existing seven-gate, manual-authority and public-quote separation remain unchanged.

## Quote certification and manual authority

**BLOCKED.** Yahoo and Stooq are public research inputs, never certified execution quotes. No eligible sealed manual authority was created.

## Next exact action

During a NYSE regular session, with a newly exported sanitized Host envelope, run:

```powershell
& ".\scripts\run_production_acceptance.ps1" -Snapshot "C:\Inputs\today.json"
```

It runs existing canonical doctor, safe pending migration if present, snapshot validation, data-status and—only when validated input and regular session are present—canonical daily. It does not edit policy, manufacture data, invoke an adapter directly, wait for market open, or submit orders. Inspect the generated `reports/controlled-improvement-phase1-live-acceptance.json` before considering any status promotion.

## Promotion verdict

**ENGINEERING VERIFIED; PRODUCTION NOT VERIFIED.** Do not enter Controlled Improvement Phase 2 until a real Host snapshot, a fresh open-session market probe, and a canonical live research-to-decision record have been captured.

