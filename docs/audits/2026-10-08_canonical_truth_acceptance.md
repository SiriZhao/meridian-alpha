# Canonical truth hardening acceptance — 2026-10-08

## Baseline

- Initial branch: main; clean working tree.
- HEAD and fetched origin/main: 1d7e0643ed53a805d2691bc8e42592fe53d28280.
- Remote: https://github.com/SiriZhao/meridian-alpha.git.
- Development branch: codex/canonical-truth-hardening, created from origin/main.
- Baseline offline suite: 561 passed, one Windows process-tree cleanup failure
  in the restricted sandbox. The unchanged test passed under approved host
  execution (1 passed, 1.77 seconds). No assertion was relaxed.

## Accepted changes

See ADR 0032 for the architecture and backward-compatible migration contract.
One sealed typed canonical_state now feeds health, the Markdown audit,
legacy display fields, CLI summary and redacted report-query summary.
The canonical-state JSON schema is checked against the typed model; the
existing paper/health v1 envelopes accept the additive state.

Known research-status, empty provider telemetry, false SKIPPED and missing
confidence defects are fixed. Missing measurements are distinguished from
known nonexecution. Zero confidence is preserved. Publication schemas do not
turn public research quotes into certified execution quotes.

Additional fixes cover late duplicate NAV writes, failed-marker retry,
attempted versus committed paper intent counts, ledger mutations without a
version increment, stale successful report-failure snapshots, misleading
missing-schema validation labels, and CLI exit codes for PAPER_READY and
PAPER_WAITING_FOR_MARKET. The latest-report query now sees final paper receipts
and labels COMPLETE / INCOMPLETE / INVALID / LEGACY_UNVERIFIED publication.

Health publication uses the shared exclusive cross-device fallback. A final
report_bundle.json records all three artifact hashes after consistency checks.
Its verifier checks expected filenames, hashes and canonical identity. Missing
or invalid receipts never prove a completed bundle.

## Validation

- Final scripts/validate_repo.py: Ruff PASS; Pyright 0 errors, 0 warnings;
  full offline pytest **606 passed in 81.56 seconds**; CLI help smoke PASS.
- Net addition: **44 tests** (43 projection tests and one late-race integration
  regression). The existing failed-marker regression was strengthened to
  require actual successful recovery and authoritative ownership.
- Scenario coverage: first NO_ACTION, simulated intents/fills, provider fallback,
  native research success, research fallback/unavailable, early duplicate,
  explicit prior-run reuse, blocked quote certification, closed market,
  degraded optional metadata with valid deterministic decision, hard blocker.
- Additional contracts: nullable/zero confidence, legacy unknowns, immutable
  source selection, visible/structured artifact drift, authority violations,
  partial publication, tampering, schema parity, redaction and final query state.
- Fresh subprocess tests check actual CLI summaries and exit codes for all
  twelve scenarios. Another subprocess reloads and validates the report bundle.
- Independent Python -O archival report-generation smoke PASS. Projection
  consistency checks explicitly raise on mismatch and survive optimized Python.
- All tests automatically isolate MERIDIAN_HOME and MERIDIAN_CACHE, including
  child processes. The final full suite ran through approved host execution.
- Reviewed source diff and git diff --check PASS before publishing.

## Historical evidence comparison

Read-only source: 2026-10-07 daily-669e33c15df37596c836ff68 and its paper receipt.
An isolated archival reprojection recovered research AVAILABLE, confidence
0.9303, providers nasdaq/yahoo, fallback SPY:nasdaq, decision NO_ACTION and
PAPER_NO_TRADE. Archived research is marked INHERITED, with explicit
REUSED_EXISTING_CANONICAL_RUN and zero current ledger/order/fill side effects.
The source daily JSON, paper JSON, health JSON and Markdown hashes remained
unchanged. This is historical projection validation, not a new canonical run.

Generated comparison artifacts live under ignored repository-local
.tmp/historical-projection-comparison and .tmp/historical-projection-final.
They are not production reports and are not included in the commit.

## Safety and remaining boundaries

Schwab-Paper remains the canonical paper account. Broker submission remains
DISABLED; no broker code, credentials, real orders or live order side effects
were introduced. GPT remains advisory. No sizing, price, allocation, risk gate,
production policy or forward-evidence promotion rule changed.

Paper orchestration changed only to preserve authoritative ownership, allow
already-permitted failed-marker recovery and prevent duplicate NAV writes.
Test simulation created paper fills only in disposable isolated databases.
The production ledger was not executed or mutated. Historical reports were
read, not migrated or overwritten.

Limitations: legacy missing facts cannot be recovered without their saved
source; they remain UNKNOWN. Analysis and final paper receipts are distinct
phases of one canonical identity, so post-paper balances must not be compared
to pre-paper balances as though they were simultaneous. Bundle publication is
a verified final receipt rather than an atomic three-file transaction. No new
live research/provider or regular-session production acceptance is claimed.

Next phase: make any future dashboard/API consume canonical_state and verify
the report bundle, then observe the next authorized canonical daily workflow
without changing policy or recreating historical runs.
