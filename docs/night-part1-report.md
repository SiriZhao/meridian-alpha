# Meridian Alpha - Night Phase Part 1 report

## Scope and safety

This phase completed Gate 2.5 research-boundary hardening and the
Meridian-owned evidence foundation using offline, replay, fake, and synthetic
inputs only. No DeepSeek, OpenAI, TradingAgents live graph, Schwab, FinRL-X,
production market-data, paid API, cloud, or brokerage call was made. No
secret-file contents were opened.

Gate 3 has not started.

## Validation

Baseline before this phase:

- pytest: 57 passed
- ruff check .: passed
- pyright: 0 errors

Final commands and results:

- .venv\Scripts\python.exe -m pytest -q: 67 passed
- .venv\Scripts\python.exe -m ruff check .: passed
- .venv\Scripts\python.exe -m pyright: 0 errors, 0 warnings
- Runtime capability scan for place_order, submit_order, execute_trade,
  broker_login, and cancel_order: no matches in src

## Files changed

Core and contracts:

- src/meridian/schemas.py
- src/meridian/research.py
- src/meridian/config.py
- src/meridian/candidates.py
- src/meridian/evidence.py

Policies and tests:

- policies/models.yaml
- policies/data.yaml
- tests/test_night_part1.py
- tests/test_review_packaging.py

Documentation and safety tooling:

- scripts/package_review.ps1
- docs/architecture.md
- docs/product-contract.md
- docs/build-state.md
- docs/adr/ADR-004-research-boundary-hardening.md
- docs/provider-capability-matrix.md
- docs/review-packaging.md

## Research statuses and point-in-time behavior

GraphResearchSummary preserves a successful TradingAgents graph as safe
qualitative metadata. A successful graph without Meridian conviction and
provenance-bearing evidence is represented as GRAPH_SUMMARY_ONLY /
INSUFFICIENT_GROUNDING; it is never INVALID_OUTPUT and can never become an
AVAILABLE AgentSignal.

Live graph as-of safety is configuration-driven through
research.live_as_of_tolerance_seconds. Historical live requests fail closed as
HISTORICAL_LIVE_CALL_FORBIDDEN; REPLAY is the only permitted historical mode
and cannot invoke a live graph or current data source. Graph summaries record
wall-clock duration, but the pinned framework does not provide safe
cancellation, so max_graph_wall_time_seconds is currently
WALL_TIME_LIMIT_OBSERVATIONAL_ONLY.

LLM retry budget and whole-graph retry budget are separate. The development
default is llm_max_retries=1 and graph_max_retries=0; a late graph failure does
not restart the entire graph.

## Candidate and budget design

CandidateSelector is deterministic and quant-only. It uses only available
features (momentum, trend, volatility, volume ratio, drawdown, existing alpha,
and position/risk flags), never TradingAgents output. Selection priority is:

1. required review of existing holdings;
2. highest quant score;
3. explicit risk-triggered names;
4. deterministic ticker ordering.

The conservative development budget is at most three graph tickers and one
graph in flight. Candidates below minimum_quant_score are deferred unless they
are required holdings or have an explicit risk trigger. Candidates and reasons
are returned in ResearchCandidateSet; no candidate is silently dropped.

The resulting intended pipeline is:

AccountSnapshot -> Market/Quant Features -> CandidateSelector ->
ResearchCandidateSet -> Research Budget -> TradingAgentsGraph ->
GraphResearchSummary -> ResearchEvidencePacket -> Grounded Research
Normalizer -> AgentSignal -> Alpha Fusion -> Allocator -> Risk ->
Reconciliation -> Orders

## Evidence foundation

EvidenceItem now carries Meridian-owned provenance fields, including stable IDs,
provider/source, document identity, published/observed/available/retrieved
timestamps, and point-in-time status. available_at is the anti-look-ahead
authority. IDs are deterministic hashes of normalized provenance and contain no
secrets or hidden reasoning.

ResearchEvidencePacket enforces timezone-aware timestamps, no future
available_at, bounded deterministic ordering, required provenance, duplicate
rejection, provider observations, warnings, and an explicit reason for an empty
packet. EvidencePacketBuilder isolates provider failures and applies per-type
and total-item bounds. EvidenceCompletenessEvaluator returns structured
diagnostics rather than silently passing incomplete evidence.

Project-owned market, fundamental, news, and macro provider protocols expose
capabilities without leaking vendor SDK types. The included providers are
synthetic replay fixtures for AAPL, MSFT, NVDA, META, and GOOGL. They are
explicitly SYNTHETIC - NOT LIVE DATA and HISTORICAL_REPLAY_UNSAFE; they cannot
authorize executable output.

The future grounded normalizer must produce direction, research conviction,
thesis, risks, and cited evidence IDs. Every cited ID must resolve to the
packet; unknown IDs or invented provenance fail validation. No production
grounded normalizer is enabled yet.

## Safe packaging result

scripts/package_review.ps1 now excludes .env/.env.*, credential and
secret-like filenames, key/certificate material, VCS metadata, virtual
environments, vendor cache, runtime/cache/log directories, and databases. It
creates REVIEW-MANIFEST.txt before ZIP creation and fails closed if suspicious
material appears in staging. The deterministic packaging test passed using a
synthetic tree. No current secret file was read or packaged.

## Remaining High / Medium issues

High:

- No Meridian production evidence provider or grounded normalizer is connected;
  graph reports still lack sufficient provenance and numeric conviction for
  executable-path research.
- Graph wall-time is observational only because safe cancellation is not exposed
  by the pinned TradingAgents release.
- Point-in-time quality of TradingAgents internal vendors remains UNVERIFIED;
  graph output must not be reused as historical evidence.

Medium:

- Security metadata is currently a development registry/fixture; a validated
  live security master is not connected.
- Synthetic providers and replay packets are test infrastructure only and
  require replacement with independently validated, provenance-bearing sources
  before any production research claim.
- Candidate cache reuse (max_graph_age_hours) is reserved but not yet
  implemented, so graph freshness reuse is intentionally unavailable.

The system remains a deterministic, fail-closed research boundary and is not
production-ready.
