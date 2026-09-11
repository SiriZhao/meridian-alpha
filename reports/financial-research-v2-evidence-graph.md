# Meridian Financial Research V2 — Phase 3: Events, Macro and Evidence Graph

Status: **PARTIAL**. The Phase 3 contracts and focused tests pass, but the full suite has a pre-existing/cross-worktree runtime regression and therefore this phase is not declared PASS.

## Delivered

- Added `QualitativeEventEvidence`: a bounded, source-bearing event contract with stable event id, ticker/entity, headline, source reference, published/retrieved time, cutoff, event type, quality, and provenance. Events published after the cutoff are rejected.
- Added a compact macro context selector. It accepts source-bearing `MacroObservation` records and exposes only latest series known by the cutoff; missing series are omitted, not made up.
- Added a project-owned `EvidenceGraph` with node types `CLAIM`, `EVIDENCE`, `CONTRADICTION`, `ASSUMPTION`, and `UNKNOWN`; relations `SUPPORTED_BY`, `CONTRADICTED_BY`, `DEPENDS_ON`, `INVALIDATED_BY`, and `DERIVED_FROM`; and claim-level evidence/assumption/unknown references. Duplicate and dangling node/evidence/assumption/unknown references fail validation.
- Extended `MeridianResearchResult` compatibly with separately attributed `inferences`, `forecasts`, and optional `evidence_graph`. Graph evidence ids must resolve to research evidence.
- Added read-only `event_evidence` and `macro_context` MCP tools. They preserve `execution_authority: NONE`, return explicit unavailable errors, and never provide execution-quote authority.
- Updated the Astra Skill wording to allow optional cited qualitative web/event context while retaining deterministic numerical authority.
- Expanded evaluation fixtures with contradictions, cheap/deteriorating fundamentals, quality/valuation separation, weak guidance, non-material headlines, regulatory risk, insufficient data, and future-information contamination.

## Web lane

The existing opt-in web research adapter remains qualitative-only and source-bound. Its prompt forbids it from supplying prices, OHLCV, market cap, EPS, valuation, rates, VIX, or other numerical market/fundamental facts. It is not used by the Skill-facing MCP tools as a substitute for Astra reasoning or deterministic data.

## Verification

- Focused tests: `18 passed` (`test_evidence_graph`, `test_astra_foundation`, `test_web_research_agent`).
- Ruff: pass.
- Pyright: `0 errors, 0 warnings`.
- Full collection: `449 tests collected`.
- Full regression: stopped at first failure after 8 passes:
  `tests/test_acceptance_failures.py::test_canonical_cli_research_faults[ok-AVAILABLE]`
  expected `runtime_status == PASS`, received `DEGRADED`.

The failure is in the existing canonical CLI/runtime fault fixture, not a graph/event/macro assertion. No safety gate was weakened to mask it.

## Boundaries preserved

- No broker, order, account credential, cancellation, or execution surface was added.
- `execution_authority` remains `NONE` for all new research tools.
- Qualitative web/event evidence cannot overwrite deterministic market/fundamental values, clear stale/closed-market gates, or produce trade authority.
- Future events and macro observations are rejected/omitted at the analysis cutoff.

## Remaining work

Resolve the canonical CLI `PASS` versus `DEGRADED` runtime status regression, rerun all 449 tests, then stage the scoped implementation against the intentionally dirty worktree and perform a fresh-host Astra MCP smoke when its ACL/MCP discovery blocker is resolved.
