# Canonical report truth and projection contracts

Status: Accepted, 2026-10-08. Reporting boundary only; deterministic financial
policy, public quote certification and broker authority are unchanged.

## Problem and evidence

The 2026-10-07 analysis `daily-669e33c15df37596c836ff68` recorded market PASS,
research AVAILABLE, successful native research roles, confidence 0.9303,
NO_ACTION and fallback SPY:nasdaq. Its paper receipt recorded PAPER_NO_TRADE.
Health looked at a top-level research status instead of research.context,
initialized provider lists to empty, and invented inheritance for unrecorded
stages. Paper Markdown unconditionally declared all work SKIPPED and read
confidence only from the adapter structured response. Paper receipts also
dropped native intelligence and canonical stages.

## Decision

`CanonicalRunSnapshot` is sealed into `canonical_state` before publication.
Nested typed states represent market, advisory research, deterministic decision,
paper execution, idempotency and stage provenance. The snapshot retains public
observations, provider probes, advisory intelligence/details, order drafts and
paper fills. It contains sanitized summaries, never a raw AccountSnapshot.

Business result and stage execution are separate. Execution vocabulary is
EXECUTED, INHERITED, REUSED, BLOCKED, FAILED, NOT_REACHED, NOT_APPLICABLE, UNKNOWN.
Idempotency vocabulary is EXECUTED_THIS_RUN, REUSED_EXISTING_CANONICAL_RUN,
IDEMPOTENCY_BLOCKED_DUPLICATE, NOT_APPLICABLE, NOT_REACHED, FAILED. Open business
result strings preserve older provider statuses rather than silently renaming
them to a generic READY. Every stage carries a source and optional source ID.

New paper receipts preserve recorded analysis stages and their canonical
source ID, plus the paper execution stage. CANONICAL_RUN identifies the source
of the evidence; it does not itself mean reuse or inheritance. A stage performed
in this workflow remains EXECUTED. Explicitly reused historical evidence has
execution_state REUSED and an authoritative source ID.

`canonical_snapshot` is the sole legacy compatibility reader. Once a snapshot
exists, consumers use it, never legacy fields or fresh provider/ledger reads.
Health is a projection, Markdown has a human audit table and a lossless typed
receipt, CLI has `summary`, and status dimensions/readiness remain recorded
producer facts. Unmeasured stage execution is UNKNOWN, distinct from explicitly not reached.
Missing values stay null/unknown; 0 and false remain facts.
Unrecorded stages never imply PASS, INHERITED or known nonexecution. Cache counters and duration
without recorded measurements stay null. Target positions never imply holdings.

Analysis and paper receipts are two phases of one logical canonical run.
`canonical_run_id` identifies analysis; `paper_run_id` and paper `run_id` identify
the final paper receipt. A duplicate attempt has its own IDs and references the
authoritative existing owner through idempotency; it does not impersonate that
owner or claim its work/fills as current. Daily and paper artifacts are checked
within their phase; consumers must not compare pre-paper and post-paper cash
without acknowledging this boundary.

## Compatibility and migration

Existing meridian-paper-daily.v1 and meridian-run-health.v1 contracts retain
their names and legacy properties. New fields are additive; the JSON schemas
allow old receipts without canonical_state. New writers always emit it.
Legacy status SKIPPED remains readable, with explicit NOT_REACHED execution;
unknown values are not repaired into success. Old normal paper receipts may
lack stages/intelligence. Read their surviving context/confidence/probes, and
leave missing evidence unknown. Never fetch current account/market data to
backfill history. Historical files are not rewritten by this migration.

The new canonical-state schema is meridian-canonical-run.v1. There is no
breaking paper/health version migration. Strict Pydantic parsing validates the
snapshot, while older envelopes remain extensible. Schemas ship in the wheel.

## Publication and failure behavior

JSON, Markdown and health are individually staged and atomically published
where supported. The shared cross-device fallback exclusively creates a new
destination and refuses to overwrite an existing receipt. Health no longer
truncates a destination in its Windows cross-device fallback.

`report_bundle.json` is published last, only after cross-artifact validation,
with SHA-256 hashes of all three files. Report publication and finalization
are receipt lifecycle operations, not synthetic business workflow stages. New consumers use
`verify_report_bundle` before treating a bundle as complete. This is a commit
receipt, not a multi-file filesystem transaction. A partial failure may leave
files; absence of a valid matching final receipt means incomplete. Business
execution cannot be undone by a report failure, and must never be retried
blindly. Projection errors are explicit diagnostics; the report failure
wrapper preserves run identity and the original decision and updates overall
failure truth instead of returning a stale successful snapshot.

Both early and late duplicate paths avoid NAV writes. Committed ownership is
restricted to PAPER_COMPLETE/PAPER_NO_TRADE; failed markers stay retryable.
Ledger mutation includes daily ownership/NAV writes even when ledger_version
and fills do not change. The transaction guard remains race-safe. Intent count
on a losing duplicate is zero; attempted intents are separately recorded.

## Validation and safety

`assert_report_projection_consistency` compares typed snapshots, the visible
audit table, health business fields and CLI summary. Regressions cover A-L,
nullable/zero confidence, legacy unknowns, explicit reuse, adversarial drift,
authority violations, partial publication, hash tampering, late duplicate races,
failed-marker retry and fresh-process CLI/receipt loading.

An autouse test fixture isolates MERIDIAN_HOME and MERIDIAN_CACHE, including
subprocesses. Host execution is required for process-tree cleanup validation.
No production policy promotion, live broker code, certified public execution
quote, real orders, or account inference is introduced.
