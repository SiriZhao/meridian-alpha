# Meridian Alpha resilience acceptance — 2026-10-08

## Baseline and scope

- Continued branch: `codex/canonical-truth-hardening`.
- Starting HEAD: `b8f0f00d812e74b7b85398214071c25610687d06`.
- Starting worktree: clean. Remote: `https://github.com/SiriZhao/meridian-alpha.git`.
- Prior phase: 606 tests. This phase adds 74 failure/contract regressions.
- Trading thresholds, sizing, share quantities, limit-price algorithms and
  production policy are unchanged. Data/research/outcome acceptance is stricter.
- No canonical runtime command or ledger write was performed. All test/cache/
  paper/report writes used isolated paths under the repository.

## Verified results

| Check | Result |
| --- | --- |
| `python scripts/validate_repo.py` | PASS |
| Ruff | PASS |
| Pyright | 0 errors, 0 warnings |
| Full offline pytest | 680 passed in 87.18 seconds |
| Provider/research/forward/failure targeted suite | 124 passed in 6.02 seconds |
| New resilience contract module | 74 collected, all included in passing suites |
| CLI help | PASS |
| Fresh Python `-O` paper/report/CLI smoke | PASS |
| Cross-artifact projections and report bundle hashes | PASS |
| Real read-only public quote smoke | Both providers OK; public certification BLOCKED |
| Whitespace/diff review | PASS |

The new module checks structured provider facts and typed canonical snapshots.
Ten quote failure combinations also persist and compare canonical JSON, Markdown,
run health and CLI payloads. Forward projection drift is rejected independently
of the embedded canonical receipt. Pre-extension canonical forward facts are
preserved; explicitly sealed empty values remain authoritative.

## Failure matrix

| Injected condition | Verified behavior |
| --- | --- |
| Yahoo timeout / malformed JSON / schema drift | Classified failure retained; fresh secondary selected |
| Primary stale, secondary fresh | FALLBACK; primary STALE_DATA retained |
| Primary fresh, secondary stale or timeout | PRIMARY; secondary failure remains visible |
| Both providers fail | NONE or validated fresh CACHE; no invented quote |
| Source/availability after cutoff or clock skew | Invalid observation excluded |
| Cross-source disagreement | Market degraded/blocked; conflicting quote not cached |
| Quote cache corrupt, invalid UTF-8, wrong symbol, NaN or stale | No live selection; corrupt content quarantined uniquely |
| Cache identity separator collision | Digest keys remain distinct |
| Historical primary stale or failed | Secondary attempted; attempt chain preserved |
| Historical cache corrupt or retrieved after replay cutoff | Cache rejected; providers attempted |
| Valid history but cache write fails | Valid data retained; WRITE_FAILED exposed |
| Live fails vs history fails | Missing market input remains explicit; stages remain distinct |
| Premarket, after-hours, scheduled closure, holiday | Exchange context explicit; public authority never promoted |
| Yahoo misaligned history arrays / invalid epochs / wrong shape | Typed malformed provider failure |
| Nasdaq incomplete daily bar and numeric zero volume | Incomplete session excluded; zero retained |
| LLM timeout / unavailable / malformed or empty output | No false research READY; advisory boundary retained |
| Supported claim without supporting evidence | Schema rejected; sanitized rejection metrics retained |
| Four roles in one shared invocation | One measured process duration; role elapsed times null |
| Rejected/expired/late-publication existing evidence | Retrieval not suppressed |
| Open retrieval circuit | Bounded within one retrieval; next retrieval probes recovery |
| Non-retryable empty provider response | EMPTY_DATA; one actual attempt, no invented retries |
| Research memory from after cutoff | Excluded from current research |
| Forward missing/delisted/late intraday price or unknown corporate actions | Outcome pending; no guessed return |
| Late delivery of a correctly dated, verified close | Ingested once; evaluation only after delivery cutoff |
| Forward publication failure / stale writer / lock contention | Memory rollback, reload and explicit retry; no lost records |
| Duplicate/corrupt outcome and verified provenance mismatch | Load/write rejects inconsistent records |
| Sample threshold reached | EVALUATION_ELIGIBLE for review; NO_AUTOMATIC_PROMOTION |

Existing tests additionally cover holiday/DST horizon calculation, quote gates,
paper idempotency, hard blockers and execution certification separation.
No tests were skipped, xfailed or weakened to conceal failures. Changed legacy
assertions now require specific failure categories, preserved quarantine bytes,
rejected ungrounded claims and verified-sample counts.

## Fresh process and public evidence

Fresh process isolated runtime:
`.tmp/resilience-smoke-69c92ec5ebf94f8099791758f3b786c7`.

- NO_ACTION fixture: PAPER_NO_TRADE, orders/fills 0/0.
- Controlled fill fixture: PAPER_READY, paper orders/fills 1/1.
- Both repeats: PAPER_ALREADY_EXECUTED, no duplicate fill.
- Report bundle verification, canonical/Markdown/health/CLI consistency and a
  separate CLI `paper status` process passed under Python optimization.
- Broker submission DISABLED; broker side effects false; canonical runtime not written.

Actual public-data diagnostic time: `2026-10-07T18:20:24.508760+00:00`, obtained
from the host clock without a session/date override. Yahoo SPY latency was
519 ms; Nasdaq 327 ms. Both were OK, selected lane PRIMARY, quote age 2.509 s,
session REGULAR, provider session INCOMPLETE (last-only public observation).
The quote stayed PUBLIC_RESEARCH_QUOTE / BLOCKED. This diagnostic did not run
GPT research, create paper orders, touch the production ledger or constitute a
fresh canonical daily acceptance run.

## Performance measurement

The final isolated, three-bar history fixture measured one cold retrieval at
10.681 ms, then 30 cache reads with median 0.433 ms and observed p95 1.869 ms.
Provider call count stayed one. The quote matrix also verifies deduplicated
symbols request each quote provider once. Shared research tests measure exactly
one invocation for four logical roles. These are fixture measurements, not
production benchmarks. No speculative routing, timeout or parsing optimization
was applied; secondary cross-checking remains intentional.

## Compatibility, safety and remaining boundaries

See ADR 0033 for taxonomy, health windows, cache refetch strategy, v1/v2 forward
reading and additive canonical/health schema compatibility. Production ledgers
and historical reports were not migrated, reset or rewritten.

Permanent invariants remain Schwab-Paper, DISABLED broker submission,
PUBLIC_RESEARCH_QUOTE certification BLOCKED, advisory-only LLMs, deterministic
order construction and SHADOW_EVIDENCE_ONLY / NO_AUTOMATIC_PROMOTION.

No authoritative execution feed or verified corporate-action/delisting outcome
adapter exists. Canonical intraday public snapshots therefore do not manufacture
verified horizon closes. Legacy/unverified outcomes remain readable but cannot
qualify an experiment. Health is observational, not automatic routing. Citation
validation cannot establish semantic truth of every model claim. A fresh
production GPT/canonical-cycle acceptance was not performed in this development
stage; it remains distinct from isolated paper and public-data validation.

Recommended next work: build a read-only, corporate-action-aware dated close
adapter and review its outcome evidence manually; expand sustained provider/SLO
measurements before considering deterministic routing changes. Keep all promotion
and execution authority outside the research/evidence pipeline.
