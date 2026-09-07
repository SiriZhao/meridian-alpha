# Controlled Improvement — Phase 1 / Batch 1

Status: engineering closure PASS; production reality acceptance DEGRADED.
Recommendation and manual execution remain BLOCKED. No broker integration,
orders, optimizer changes or LLM model replacement were introduced.

## Git and resume evidence

Starting HEAD: `c81eddc`. The resumed workspace was already on
`astra/controlled-improvement-phase1` with unfinished Phase 1 changes and two new
test files. They were reviewed and retained, not overwritten from the old 304-test
baseline. Repository and installed Skill already matched the Phase 1 workflow.
User modification `reports/gate6g-quote-preflight.json` remains uncommitted.

Implementation commits: `1d9fe5c` (domain/SQLite) and `fb7fbaf` (daily/providers).
Ending implementation commit: `fb7fbaf079d24cb1ec191d7410386856d8b7072d`.
The following documentation commit records this evidence; see Git log for its
hash. No push or release tag was performed.

## Changes

- Existing host readiness vocabulary now provides typed dimensions and computed
  research/recommendation/manual outcomes. UNKNOWN and NOT_RUN never imply PASS.
  This diagnostic model does not replace the sealed seven-gate authority.
- Host diagnostics validate explicit as_of/retrieved_at, coverage, pending state,
  schema and source hashes. SQLite claims snapshot identity/facts atomically;
  replay and conflicting identity are explicit. Validation alone does not claim.
- SQLite v1 → v2 adds snapshot_receipts and run_readiness in the existing DB.
  Upgrade is transactional and idempotent, preserves user tables, rejects newer
  schemas and closes connections. Failure rollback and concurrent claims tested.
- Provider probes include actual request/receipt times, source time, cutoff,
  session, cache selection, both lanes and final outcome. Stale primary does not
  veto valid secondary via a false price conflict. Cache retains provider aliases.
- Live cutoff closes after quote/history receipt; fixed historical adapter cutoff
  no longer silently advances. Final provider health agrees with final freshness.
  Holiday timestamps cannot masquerade as fresh trades. Historical age counts
  sessions; older closing prices remain context, not freshness exceptions.
- Daily JSON/Markdown and AuditStore persist readiness, provenance, blockers and
  next actions. Missing/replayed/malformed inputs produce diagnostics. Existing
  0/2/3 CLI exits and canonical launcher remain compatible.

## Verification

Resume baseline: 333 tests PASS (19.03 s), Ruff PASS, Pyright zero errors/warnings.
Final: 337 tests PASS (16.60 s), Ruff PASS, Pyright zero errors/warnings.
Commands use `.venv/Scripts/uv.exe run --no-sync` for pytest -q, ruff check .,
and pyright. No environment synchronization or package changes were needed.

Tests cover missing/stale/future/invalid/duplicate/pending snapshots, DST,
Chinese/space/# paths, UNKNOWN aggregation, uncertified quotes, provider failure,
fallback/cache, fixed/live cutoff, expired final observations, report/JSON and
DB persistence, v1 upgrade, newer-schema rejection and transactional rollback.

## Real probes

Fresh isolated temporary MERIDIAN_HOME; production DB was not used.
Init exit 0, doctor PASS, missing-snapshot daily exit 2 with persisted BLOCKED
report. Actual public data-status exit 2: Yahoo STALE, Stooq UNAVAILABLE across
AAPL/MSFT/NVDA/SPY. Probe timestamps and errors are in
[evidence](evidence/controlled-phase1-resume-reality.json).
Earlier interrupted-run evidence is retained separately. No new real Host
snapshot was supplied. Synthetic tests do not count as real account acceptance.

## Readiness and remaining limits

Runtime PASS; snapshot BLOCKED/source UNKNOWN; market BLOCKED; provider
provenance PASS means actual requests recorded, not provider availability.
Research NOT_RUN, research freshness UNKNOWN, policy/decision NOT_RUN for the
missing-input probe; execution quote, recommendation and manual readiness BLOCKED.
Configured credentials and adapter imports were not promoted to provider PASS.
Canonical operational example policies/sector metadata remain uncertified.

Known limits: scheduled calendar excludes unscheduled closures/halts; claims
remain consumed on downstream failure; hashes do not authenticate a Host;
SQLite and files are not one transaction. Failed storage never implies a
persisted report. Fresh-data history and full certified research acceptance
remain unverified. See [machine summary](evidence/controlled-phase1-summary.json).

## Batch 2 preparation

Batch 1 engineering criteria are met. Batch 2 preparation is ready; production
promotion is not. The next bounded work is Host provenance acceptance, existing
certified research input/evidence closure, fresh-session provider validation and
partial-persistence diagnostics. Keep missing evidence BLOCKED. Do not add new
strategies, execution, models or certification shortcuts.
