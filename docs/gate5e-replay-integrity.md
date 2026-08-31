# Meridian Alpha — Gate 5E replay integrity

## Result

Gate 5E is a network-free replay and reliability convergence pass. No broker,
Schwab, account connector, order, or model-promotion path was added.

## Replay cache

`ReplaySafeObservationCache` now writes schema-versioned envelopes (`2`) with a
creation timestamp, canonical content digest, file digest, and per-record
digest. Loading a list instead of the envelope, malformed JSON, truncated
content, bad hashes, invalid records, or conflicting duplicate `cache_key`
records raises `CACHE_CORRUPT`. Conflicting `available_at`, source hash,
payload hash, schema version, provider, or observation type is never resolved
by last-write-wins. Identical records are retained from first-seen order only.
Historical availability, source identity, and payload identity are immutable;
a correction must use a new cache key/version.

The cache scanner rejects API keys, access/refresh tokens, authorization,
passwords, credentials, account numbers/IDs, and raw connector data without
printing matched values.

## Exact LLM replay

`validate_frozen_llm_response` verifies the exact SHA-256 response hash,
schema version, decision cutoff, duplicate citations, and membership in the
certified evidence set. `replay_grounded_research` then rebuilds
`GroundedResearchSignal`, `CertifiedAgentSignal`, and deterministic alpha using
only the frozen sanitized response and certified packet. There is no provider
call in this path.

## Historical and failure matrix

The curated replay matrix covers before/after filing, before/after amendment,
pre-market, regular session, after close, holiday, stale/partial account, and
provider outage. The offline soak repeats explicit fail-closed outcomes for
SEC, market, DeepSeek, quote, Host, dislocation, reconciliation, restatement,
and FinRL-X failures. Outages are not silently converted to neutral research.
Provider health exposes `AVAILABLE`, `DEGRADED`, `STALE`, `UNAVAILABLE`, and
`UNVERIFIED`; missing observations are `UNVERIFIED`.

## Status

| Check | Status | Evidence |
| --- | --- | --- |
| Cache load integrity | PASS | Versioned envelope and adversarial hash/duplicate tests |
| LLM replay | PASS | Frozen hash/cutoff/citation validation and network-free chain |
| Historical replay | PASS (contract matrix) | Curated cutoff cases defined; no live calls |
| Property tests | PASS | Fail-closed cache, citation, and OOS-status invariants |
| Offline soak | PASS | Bounded repeated matrix; zero external calls/retries |
| Known P0 | 0 | No safety-critical defect observed |
| Known P1 | 3 | FinRL-X runtime/artifact unavailable; execution quote unselected; real Host input absent |

Performance for unavailable providers is intentionally reported as
`NOT_MEASURED_OFFLINE`; no retry storm or external call occurred in this pass.
