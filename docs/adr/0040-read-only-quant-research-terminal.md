# ADR 0040 — Read-only Quant research terminal

Status: accepted for research development; no strategy promotion.

## Context

The native live bridge already computes V2.2, but MCP only exposes legacy
bar diagnostics. Read-only MCP annotations did not prevent writable cache,
directory and audit-store paths. Operator reports must keep numerical evidence
inspectable independently of a model outage.

## Decision

Reuse `build_research_packet`, `RiskEngine` and native four-role orchestration.
Expose three new capabilities: one aggregate Quant snapshot, an isolated
weight/shock what-if and exact evidence trace. Do not add separate factor,
ranking or regime aliases, a numerical optimizer, provider or state store.

Enforce read-only connections, suppress runtime directory creation and provider
cache/health writes in MCP paths. Default approved-host operational paths retain
their existing behavior. CLI terminal reads one bounded explicit input and
prints seven views to stdout before any application-service construction.

Hash/cutoff-bound numerical views precede inference. Model values cannot replace
authoritative rows. Exact pointer/value citations validate numerical
correspondence; uncontrolled numerical role prose is refused. Existing subjective
confidence/scenario values remain explicitly UNCALIBRATED; decision briefs omit
scenario probabilities. Semantic truth and source authentication still require
independent review.

The planner is a fixed allowlist with bounded in-memory Quant memoization.
It neither installs nor invokes source-proposed tools. Skill workflows inherit
explicit time/tool/no-nested-model budgets. There is no disk conclusion cache.

## Consequences

Python contracts and JSON schemas, Chinese text/JSON terminal, sanitized risk
diagnostics and native explanation scorecards are independently testable.
Rejected histories produce null scores/ranks and WAIT, not optimistic sorting.
Source classes and unknown execution/ETF/correlation inputs remain visible.

No canonical algorithm coefficient, ledger schema, original experiment archive,
portfolio hard constraint, account or broker authority changes. Historical
certification is caller attestation, not financial evidence authentication.
Real adjusted-history coverage and external live model acceptance remain blockers.

## SQLite journal boundary amendment

An isolated WAL regression showed that `mode=ro` can create `-wal` and `-shm`.
This matches [SQLite's read-only WAL contract](https://www.sqlite.org/wal.html#read_only_databases).
Read-only storage now refuses WAL-mode headers and existing WAL/shared-memory/
rollback-journal files before SQL execution, with
`READ_ONLY_JOURNAL_REVIEW_REQUIRED`. It neither checkpoints nor changes journal
mode. Using `immutable=1` for an active account would risk ignoring committed WAL
state, so that shortcut is prohibited. Missing/schema/corruption and journal
refusal remain distinct. OS read-only permissions are still required against
concurrent journal-mode reconfiguration; the application guard is not a sandbox.
