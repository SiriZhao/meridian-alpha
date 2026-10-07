# ADR 0033: Observable provider failures and verified forward outcomes

Status: accepted. Extends ADR 0032 without brokerage execution capability.

## Problem

Provider errors were represented by coarse status strings. A missing selected
quote could compare equal to a missing primary quote, falsely selecting PRIMARY.
Conflicting observations were cached before disagreement validation. Historical
fallback accepted stale primary data and cache files lacked sufficient integrity,
request-range and cutoff checks. Research roles inherited shared wall time that
the shadow evaluator summed four times. Empty research output could retain
SUCCESS. Forward outcomes could use a later intraday price as a horizon close,
and failed publication could leave in-memory records ahead of disk.

## Decision

`provider_resilience.FailureCategory` defines the common machine vocabulary:
TIMEOUT, RATE_LIMIT, HTTP_ERROR, INVALID_RESPONSE, SCHEMA_DRIFT, EMPTY_DATA,
STALE_DATA, SESSION_MISMATCH, SYMBOL_NOT_FOUND, NETWORK_FAILURE,
PROVIDER_FAILURE and UNKNOWN. Classification uses exception types, safe codes,
HTTP status and wrapped causes. Exception bodies and URLs are not stored in health.

Quote and historical attempts preserve requested provider, start/end, latency,
raw/normalized category, selection and fallback evidence. Successful observations
also preserve source/receipt times, freshness, session and public provenance.
Final quote validation records both the attempt category and final category;
slow historical collection can make a previously successful quote stale.

`ProviderHealthStore` uses a separate SQLite telemetry file in the corresponding
cache directory. Writes and pruning are transactional. It retains at most 256
attempts per provider/channel and summarizes the newest 32: consecutive failures,
recent successes/failures, categories, observed symbols, fallback count and
recent/prior latency means. LIVE and REPLAY channels are distinct. Three
consecutive failures report UNHEALTHY; previous failures in the window report
DEGRADED. A success resets the consecutive counter. MULTI_SYMBOL_OBSERVED is
an observation, not a claim of global outage. Health never changes routing.
Telemetry failure reports TELEMETRY_UNAVAILABLE and cannot discard good data.

Routing remains deterministic: request the primary and secondary once for
cross-source validation; prefer fresh primary, then fresh secondary, then a
validated fresh cache entry. A conflict blocks the market result and cannot
publish the conflicting quote into cache. Both failed providers select NONE.
Cache provenance remains public research provenance, never primary impersonation.
Every public quote retains PUBLIC_RESEARCH_QUOTE / certification BLOCKED.

Historical cache entries require an integrity hash, exact request bounds,
canonical identity, current completed session and no future source/availability/
receipt time. Stale primary data falls through to the next provider. Cache write
failure preserves valid historical data and records WRITE_FAILED. Nasdaq
excludes incomplete session bars and retains numeric zero volume. Yahoo rejects
misaligned arrays and invalid epochs; malformed public responses become typed
provider failures. No data is fabricated or forward-filled.

Research circuits bound one retrieval, then permit recovery probing next time.
Retries are bounded and actual attempt counts are reported. Rejected, expired
and unavailable-at-cutoff evidence cannot suppress retrieval. Explicit source
availability is separate from later assembly/retrieval time; absent availability
uses receipt as the conservative boundary. Canonical input references are already
bound to the supplied cutoff, and deterministic derived evidence inherits input
availability. Research memory later than the analysis cutoff is excluded.

Native research READY requires four typed, validated role outputs. The advisory
authority is a literal invariant. Empty/non-object or malformed output is a
schema failure; supported claims without evidence references are rejected.
Sanitized rejected numeric-claim counts remain visible to the shadow evaluator.
Legacy adapter `output`/`structured_response` omission is intentional: native
outputs live in `research_intelligence.{primary,skeptic,scenarios,synthesis}`.
Confidence includes composer version/provenance and independent model
self-confidence. ConfidenceComposer.v1 is unchanged: data quality 25%, coverage
20%, source diversity 10%, GPT consistency 15%, skeptic quality 15%, scenario
coherence 15%. Missing-role defaults are diagnostic components, never proof of
research availability or an execution-authority gate.

Shared invocation IDs identify one process. Legacy role `duration_ms` remains
for compatibility but is explicitly NON_ADDITIVE_SHARED_PROCESS. Role elapsed
time and independent effective deadlines are null for shared execution; configured
role budgets are descriptive. Health, application summaries and shadow evaluation
do not sum those four role wall times. The application records measured total
research wall time. Independent-role timings remain independent.

Forward ledger writes acquire an OS guard, reload current disk state, validate
immutability and atomically fsync/replace. A failed write rolls back memory.
Contention is explicit and retryable on the next call; no silent lost update is
permitted. Load rejects duplicate authorities, conflicting outcomes, unknown
schema versions and immature/inconsistent verified outcomes.

`ForwardPriceObservation` supplies a dated session close and corporate-action
coverage. Late delivery is acceptable only when its source timestamp is the
exact maturity close and both symbol/benchmark prices have NONE_VERIFIED coverage.
Unknown actions, adjusted prices without an adjusted inception basis, missing
or delisted symbols, and late intraday quotes remain pending. Canonical public
intraday snapshots intentionally supply no verified outcome observations.
Legacy undated ingestion at exactly maturity remains readable as UNVERIFIED.
Only verified horizon-close outcomes with benchmark returns count toward
evaluation; missing benchmark returns are never substituted with zero. Evaluation
is cutoff-bound and excludes outcomes whose delivery/observation time is later
than the canonical cutoff, even when their source price belongs to an earlier close.
EVALUATION_ELIGIBLE is human review readiness only. SHADOW_EVIDENCE_ONLY and
NO_AUTOMATIC_PROMOTION remain permanent, including after the sample threshold.

## Compatibility and projections

Report/health schema versions remain v1 with additive telemetry. Canonical state
adds `forward_evidence` and projects it to health/CLI/Markdown. Pre-extension
canonical states import the already-recorded enclosing forward fact only when
the new field is absent; a sealed explicit empty value is authoritative.
The projection consistency assertion covers that health field as well.

Forward ledger v1/v2 records are parsed with defaults; legacy unverified outcomes
are retained but excluded from evaluation. No production migration runs here.
Old cache entries without integrity/request metadata become cache misses and are
refetched. Quote cache keys add a digest of the provider/symbol pair to prevent
separator collisions; old files are retained. Corrupt quote files are quarantined
under unique names. These disposable-cache changes do not rewrite user ledgers.

## Limits

No certified execution feed, verified corporate-action outcome adapter, automatic
delisting return assumption, automated promotion or provider-health-based routing
is introduced. Evidence citation checks establish references, not semantic truth
of arbitrary model prose. Human research review remains necessary. Health windows
are small diagnostic samples; they are not service availability guarantees.
Measurements use controlled fixtures; no production latency claim or speculative
performance optimization follows from them.
