# Meridian Alpha — Night Phase Part 2 report

## Scope and safety

Night Phase Part 2 was completed offline/replay-first. No live provider was
enabled and no network request was made. The work stops before supervised Gate
3B data integration.

Explicitly:

- **NO LIVE DEEPSEEK REQUESTS WERE MADE.**
- **NO LIVE TRADINGAGENTS REQUESTS WERE MADE.**
- **NO SCHWAB CONNECTION WAS MADE.**
- **NO BROKER EXECUTION CAPABILITY EXISTS.**
- No FinRL-X, production market-data, paid API, cloud, tag, or push operation
  was performed.
- No `.env*` or other secret-file contents were opened, printed, copied, or
  packaged.

## Validation

- Starting test count: 90 passed at the Gate 2.6 baseline.
- Ending test count: 101 passed after Gate 2.6 convergence repairs.
- Commands: `.venv\Scripts\python.exe -m pytest -q`,
  `.venv\Scripts\python.exe -m ruff check .`, and
  `.venv\Scripts\python.exe -m pyright`.
- Review archive command: `scripts\package_review.ps1` with the requested
  `artifacts\meridian-alpha-review.zip` and manifest paths.

## Files added or changed

Part 2 introduced or updated the following non-secret paths:

- `src/meridian/research.py`, `src/meridian/pipeline.py`, `src/meridian/config.py`,
  `src/meridian/evidence.py`, `src/meridian/candidates.py`,
  `src/meridian/reporting.py`, `src/meridian/audit.py`, and `src/meridian/cli.py`
- `tests/test_night_part1.py`, `tests/test_night_part2.py`,
  `tests/test_night_part2_e2e.py`, `tests/test_night_part2_config.py`, and `tests/test_review_packaging.py`
- `policies/models.yaml` and `policies/data.yaml`
- `schemas/examples/SYNTHETIC_AAPL_GRAPH_SUMMARY.json`
- `scripts/package_review.ps1`
- `docs/build-state.md`, `docs/architecture.md`,
  `docs/product-contract.md`, `docs/review-packaging.md`,
  `docs/provider-capability-matrix.md`,
  `docs/adr/ADR-004-research-evidence-and-grounding.md`,
  `docs/adr/ADR-005-candidate-screening-and-research-budget.md`,
  `docs/gate3b-live-data-plan.md`, and this report.

## Research statuses and point-in-time protections

`GraphResearchSummary` preserves a successful TradingAgents graph as bounded
qualitative metadata. A graph result without Meridian conviction and
provenance-bearing evidence is `GRAPH_SUMMARY_ONLY` /
`INSUFFICIENT_GROUNDING`, never `INVALID_OUTPUT` and never an available
`AgentSignal`. Grounded outcomes remain explicit for unavailable, invalid,
disabled-live, and provider-failure cases.

`available_at` is the anti-look-ahead authority for Meridian evidence. Packet
and citation validation reject naive timestamps, future evidence, missing
provenance, duplicate IDs, cross-ticker citations, and unverified synthetic
evidence on the executable path. Live as-of tolerance and replay-only
historical behavior remain configuration-driven. Replay loads graph summary,
evidence packet, and grounded signal as separate hash-checked artifacts and
never calls current providers.

Wall-clock duration is recorded for graph runs. The pinned TradingAgents
release does not expose safe cancellation, so the configured wall-time limit is
observational only. LLM retry budget and whole-graph retry budget are separate;
the development graph retry default is zero.

## Candidate selection and research budget

The pipeline is:

`AccountSnapshot → Market/Quant Features → CandidateSelector → bounded
ResearchCandidateSet → TradingAgentsGraph → GraphResearchSummary →
ResearchEvidencePacket → grounded normalizer → AgentSignal → Evidence Authorization → CertifiedAgentSignal → deterministic
Alpha Fusion / allocation / risk / reconciliation / orders`.

CandidateSelector uses only available deterministic quant features, prioritizes
existing holdings requiring review, then ranks by quant score and explicit risk
flags. Deferred candidates and reasons are returned. Development defaults bound
graph research to three tickers and one graph in flight; a large universe
cannot fan out into an unbounded graph run.

## Meridian evidence and grounding

`EvidenceItem` carries stable provenance fields and deterministic IDs.
`ResearchEvidencePacket` bounds item count, deduplicates deterministically,
records provider observations, and supports structured completeness diagnostics.
Offline market, fundamental, news, and macro providers are synthetic replay
fixtures only and are marked `SYNTHETIC - NOT LIVE DATA` / replay-unsafe.

`GroundedResearchSignal` requires explicit Decimal conviction in `[0, 1]`, a
valid direction, thesis, and packet-resolving citation IDs. There is no
graph-rating-to-conviction mapping. `AgentSignal` is created only after the
citation gate and point-in-time checks. `DeepSeekGroundedResearchNormalizer`
exists as code only and defaults to `live_enabled: false`; it was not invoked.

## Offline E2E results

- **Scenario A — zero capital:** `NO_CAPITAL`, no market access, no research,
  no graph, no evidence normalization, and no orders.
- **Scenario B — synthetic $50,000 cash:** bounded TEST pipeline produced a
  synthetic graph summary, Meridian evidence, and an explicitly configured fake
  grounded outcome, but issued no executable certificate or Alpha Fusion input.
  Synthetic output remains diagnostic-only and non-production.
- **Scenario C — existing holdings plus excess candidates:** existing holding
  review was selected first, the three-ticker budget was enforced, and deferred
  names were surfaced with reasons.
- **Scenario D — graph succeeds but evidence is insufficient:** result was
  `INSUFFICIENT_GROUNDING`; no available `AgentSignal` was created.
- **Scenario E — unknown citation:** result was `INVALID_OUTPUT`; no signal was
  created.

## Packaging

The safe review script stages only non-secret source paths and excludes
`.env*`, key/certificate material, credentials, `.git`, `.venv`,
`vendor_cache`, `var`, logs, caches, Python bytecode, and databases. It writes a
path-only `REVIEW-MANIFEST.txt` into the archive and a matching external
manifest. The final archive was checked by path names only.

## Remaining issues

### Critical

None introduced by this phase. No executable research claim is enabled by the
synthetic or graph-summary paths.

### High

- No production Meridian evidence provider or grounded normalizer is connected.
- TradingAgents internal vendor provenance remains unverified for historical
  replay; graph reports cannot authorize executable research.
- Graph wall-time enforcement is observational because safe cancellation is not
  available in the pinned framework.

### Medium

- Security metadata is still a development registry/fixture.
- Synthetic providers and replay artifacts require replacement with validated,
  provenance-bearing sources before production use.
- `max_graph_age_hours` is reserved for a future integrity-checked cache and is
  not used to silently reuse stale graph output.

## Next supervised Gate 3B tasks

Implement and review, one boundary at a time: execution-grade quotes,
point-in-time historical OHLCV, SEC/EDGAR fundamentals, news evidence,
security metadata, and macro data. Each adapter must declare capabilities,
freshness, timestamp availability, credentials, failure behavior, and whether
it is executable-path critical. No paid service or provider is selected by this
phase.

The system is not production-ready. Stop here until a separately supervised
Gate 3B begins.
