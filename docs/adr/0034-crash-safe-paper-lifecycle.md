# ADR 0034: Serialize paper lifecycle and preserve crash-safe projections

Status: accepted. Date: 2026-10-08.

## Problem

SQLite already prevents duplicate paper fills, but competing launches could
perform duplicate research and publish conflicting projections for one day.
Several older JSON stores also staged through fixed filenames, retained stale
in-memory state between writes, or mutated memory before a failed disk write.
Provider-health connections depended on garbage collection to close SQLite.

## Decision

The public paper-run boundary takes a per-account OS lock through snapshot,
research, deterministic decision, ledger finalization and report publication.
Contention fails explicitly before research. The SQLite `BEGIN IMMEDIATE`
transaction remains the final ledger ownership guard. Missing ledgers still
block before creating a lock or initializing an account.

First-seen, replay-observation and legacy shadow JSON stores acquire dedicated
writer locks, reload durable state while locked, enforce immutable identities,
and roll back memory when persistence fails. Writes use exclusive staging,
flush/fsync and atomic replacement. Readers reject corrupt persisted state.

Canonical JSON and Markdown reports share one exclusive, fsynced staging
primitive. Existing WinError 17/EXDEV report-publication compatibility remains
bounded to its original exception categories. The bundle manifest remains the
last publication receipt; an incomplete bundle never becomes canonical evidence.
Missing reports or health files never authorize repeating an owned paper day.
Corrupt lock metadata is retained and blocks; operators inspect ownership
instead of guessing a stale owner. OS locking is the process-lifetime guard.

Provider-health SQLite transactions close connections explicitly on success
and failure. Health observations cannot change routing or execution authority.

## Consequences and validation

Concurrency is bounded per paper account, not queued or transparently retried.
This avoids retry storms; a caller retries after the active owner exits.
Crash-abandoned staging files are not financial facts. JSON readers and report
consumers require final filenames, identities, hashes and complete receipts.
This is local-filesystem crash safety, not a distributed transaction spanning
SQLite and multiple files. A committed ledger owner survives report loss.

Regression coverage includes stale writer instances, failed replace/rollback,
corrupt envelopes, corrupt locks, live lock contention, missing report/health
artifacts, duplicate paper ownership, valid immutable shadow-outcome joins,
nonfinite outcome rejection, and no false green health from unknown states.

No brokerage surface, execution-feed authority, sizing algorithm, threshold or
production-promotion policy changes. `Schwab-Paper`, broker submission
`DISABLED`, public quote certification `BLOCKED`, advisory-only research and
`NO_AUTOMATIC_PROMOTION` remain mandatory.
