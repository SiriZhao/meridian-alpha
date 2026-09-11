# Architecture

## Current Astra Skill foundation (2026-09-11)

Acceptance is **BLOCKED_WITH_EVIDENCE**, not production-ready; see
`reports/meridian-astra-final-review.md`. The current implementation is described
here; subsequent Gate sections are historical architecture provenance.

The ChatGPT/Codex-facing intelligence layer is the active GPT-6 Astra session.
The installed `meridian-alpha` Skill directs Astra to collect evidence through
Meridian's read-only MCP tools, perform synthesis itself, and return an
evidence-first `MeridianResearchResult`. Meridian tools provide deterministic
calculations, validated account/market/fundamental context, forward evidence,
daily closure, and sanitized audit lookup. They do not call another LLM merely
to duplicate Astra reasoning.

The Astra MCP surface is:

```text
runtime_status          market_snapshot       account_snapshot
company_facts           research_packet       quant_metrics
portfolio_context       risk_analysis         forward_evidence
daily_closure           audit_lookup
event_evidence          macro_context
```

Every tool is structured-output and read-only. Responses carry source,
observed/known/cutoff times where applicable, freshness, data quality,
provenance, errors, warnings, and `execution_authority=NONE`. The canonical
application and historical research adapters remain separate compatibility
surfaces. No MCP tool exposes broker authentication or order submission.

`run_daily_analysis` and `run_host_daily_analysis` are no longer registered
tools: their legacy Python functions remain for compatibility. The canonical
daily and paper CLI can invoke their separate Codex pipeline, whereas the
Astra Skill uses deterministic tools directly. See ADR 0020.

`research_packet(symbol, analysis_cutoff)` composes market and certified SEC
data without an LLM. News and macro tools validate caller-supplied evidence;
they are not live news feeds. `quant_metrics` calculates from caller-supplied
bars and labels their provenance unverified. `company_facts` exposes current,
comparable, quarterly and debt-component facts so derived input IDs resolve.
QoQ and TTM require compatible consecutive reported quarters; missing quarters
and unavailable valuation inputs remain unknown.

`retrieved_at` is tool receipt time; missing source `known_at` remains null.
Public history remains unverified for historical information availability and
corporate-action adjustments. Live collection binds its receipt cutoff after
the provider returns; replay retains the requested cutoff. MCP filters quote
timestamps against the requested cutoff and reports collection completion
separately. Research data never certifies execution pricing.

Mutable production state is rooted exclusively in `RuntimePaths`: database,
cache, reports, logs, runs, audit, data, and runtime configuration. Repository
paths are read-only resources. The project launcher always selects
`.venv/Scripts/python.exe` (Python 3.12); system Python is not a production
runtime.

## Intent

Meridian Alpha assists a user in deciding what **manual limit orders** to enter
for a US-equity account. It is deliberately not a trading-execution system.

## Layering

```text
ChatGPT orchestration
        |
        v
AccountSnapshot (new, normalized, timestamped account fact)
        |
        v
Meridian Core
  |--> TradingAgents adapter       (optional research only)
  |--> Portfolio allocator         (deterministic fallback always available)
  |--> Risk engine                 (deterministic constraints)
  |--> Reconciliation engine       (actual snapshot vs target)
  |--> Order planner               (deterministic quantities)
  |--> Limit price engine          (deterministic prices)
        |
        v
Manual Order Ticket (human reviews and enters it through an authorized workflow)
```

## Boundary rules

`AccountSnapshot` is an input contract, not a broker client. ChatGPT or another
authorized account-data source obtains the current account state and passes a
sanitized snapshot to Meridian. Meridian Core never calls the Schwab Trading
API and has no order-submission interface.

The only future outbound product artifact is a draft/manual ticket. An order is
not known to be filled until a later, newly supplied `AccountSnapshot` proves
the resulting holdings/cash state.

## Planned package direction

```text
src/meridian/
  core/            # domain contracts, orchestration, deterministic logic
  adapters/        # optional market/research/allocator implementations
  policies/        # typed configuration loading and validation
  audit/           # sanitized run metadata and immutable decision history
  reporting/       # JSON and Markdown manual-ticket rendering
```

The domain core exposes project-owned protocols. Vendor packages must not leak
into domain models. Future adapters may call TradingAgents for timestamped,
normalized research signals and FinRL-X only for a validated, versioned model
artifact; neither may determine executable quantities or prices.

## Data and safety flow

1. Validate a new account snapshot and its freshness.
2. Acquire timestamped market data and apply a freshness gate.
3. Generate deterministic quant features and pre-screen a bounded research
   candidate set; only that set may invoke optional research and graph work.
4. Allocate targets, then apply deterministic risk constraints.
5. Reconcile only against the new account snapshot.
6. Produce deterministic order drafts and conservative limit prices.
7. Emit `READY_FOR_MANUAL_ENTRY` only from a READY `ManualReadinessCertificate`
   with all seven gates and a certified `ExecutionQuote`; otherwise fail closed
   as analysis-only, draft, or blocked.

No stage may use data after the declared analysis time.

## OpenAI integration direction

Current official OpenAI documentation describes plugins as a bundle of Skills,
MCP servers, and optional UI. The future ChatGPT-facing surface will be a
tool-only MCP server that calls this Python core; it will expose calculation /
read-only tools only. It will not expose broker login, account write, or order
execution tools.

Primary reference: [OpenAI Developers — Plugins](https://developers.openai.com/plugins)
(reviewed 2026-08-28).

## Gate 1.5 safety hardening

Account quantities/cash remain brokerage truth; executable NAV is marked from fresh quotes via ValuedAccountState. Timestamp age gates are enforced independently of freshness enums. MCP and CLI use the shared DailyAnalysisService.

## Historical Gate 2 research boundary

The following section records the superseded pre-Astra provider architecture
for audit continuity. It is not the current Skill intelligence path.

TradingAgents is an optional research-only adapter behind
`ResearchOutcome`. It cannot provide sizing, prices, leverage, or execution
instructions. LIVE and REPLAY modes are explicit; replay never invokes a live
LLM. The selected provider is DeepSeek through the official pinned
`tradingagents.llm_clients` provider registry (`DEEPSEEK_API_KEY`,
`https://api.deepseek.com`, development model `deepseek-v4-flash`). The
production adapter invokes
`tradingagents.graph.trading_graph.TradingAgentsGraph.propagate`; the
client-only structured probe is diagnostic/test-only. A successful graph is
represented as `GraphResearchSummary` inside an
`INSUFFICIENT_GROUNDING` `ResearchOutcome`: it is useful qualitative context,
but it is not an `AgentSignal` and cannot enter the executable path. The graph
does not expose Meridian conviction or provenance-bearing evidence. The
deterministic core consumes only AVAILABLE outcomes with validated
`AgentSignal` evidence. A provider failure never becomes a neutral signal.

Gate 6A makes ownership explicit: TradingAgents graph output is qualitative
second-opinion/context, while the production grounded research input is a
sealed `CertifiedEvidenceView` consumed by DeepSeek. Only a
`CertifiedAgentSignal` may reach Alpha Fusion; LLM output never owns sizing,
quantity, cash, risk, or price.

## Historical intended research pipeline

```text
Account
  -> Market Data
  -> Deterministic Quant Features
  -> Deterministic Pre-Screen
  -> Research Candidate Set (bounded by ResearchBudgetPolicy)
  -> TradingAgentsGraph
  -> GraphResearchSummary
  -> Meridian ResearchEvidencePacket
  -> Grounded Research Normalizer
  -> AgentSignal
  -> Evidence Authorization Gate
  -> CertifiedAgentSignal
  -> Alpha Fusion
  -> Allocator
  -> Risk
  -> Orders
```

The pre-screen is deterministic and does not call TradingAgents. Graph budget
controls (`max_graph_tickers_per_run`, bounded parallelism, and existing-holding
review) prevent a full-universe graph run by default. In v0.1 the graph summary
still lacks enough source/timestamp provenance and numeric conviction for
grounded normalization.

`ResearchEvidencePacket` defines the future grounding boundary. It contains a
bounded set of Meridian-owned, deterministically identified `EvidenceItem`s;
future normalization must return direction, research conviction, thesis, risks,
and cited evidence IDs, with every ID resolving to that packet. Unknown IDs,
future timestamps, and invented provenance fail closed.

TradingAgents is deep research for the bounded candidate set, not a universe
scanner. Fake/replay providers are synthetic test inputs and are never
production executable evidence. Current graph wall-time enforcement is
observational only because the pinned framework does not expose safe
cancellation; every run still records its duration and budget metadata.

Night Phase Part 2 adds a single ResearchPipelineService boundary for TEST,
REPLAY, and explicitly disabled LIVE modes. It applies CandidateSelector and
budget limits before any graph provider, builds Meridian-owned evidence, and
creates a diagnostic AgentSignal only after explicit grounded normalization and citation
validation; executable Alpha Fusion requires the separate CertifiedAgentSignal gate. A
graph rating alone is rendered as diagnostic context and is shown as RESEARCH NOT
GROUNDED when the evidence gate fails.

## Gate 2.6 safety convergence

The only executable research path is:

```text
AccountSnapshot -> deterministic quant features -> CandidateSelector
  -> ResearchPipelineService -> GraphResearchSummary
  -> ResearchEvidencePacket -> GroundedResearchNormalizer
  -> EvidenceAuthorizationService -> CertifiedAgentSignal
  -> Alpha Fusion -> allocator -> risk -> reconciliation -> orders
```

Raw `AgentSignal`, graph ratings, synthetic fixtures, replay-unsafe artifacts,
and incomplete evidence are diagnostic-only. Candidate selection is quant-only
and bounded before any graph call. `available_at` is the authoritative
anti-look-ahead timestamp; only closed PIT states are executable. A synchronized
account snapshot is required for a READY manual ticket.

## Gate 3B.1 shadow market foundation

Security identity is resolved by the project-owned `SecurityMaster` before any
quote is normalized. It distinguishes exchange calendars and provider symbols
(including `VIX` / `^VIX`) and fails closed for unknown or conflicting identity.
The project-owned trading calendar applies timezone-aware US equity/CBOE
sessions, holidays, DST and completed-session semantics.

`QuoteObservation` and `MarketDataCapabilityCertificate` are provider-neutral.
The optional `StooqQuoteProvider` is a public, last-price-only SHADOW adapter;
its observations carry provenance and freshness but are permanently
`execution_quote_grade=false`. SHADOW observations cannot authorize grounded
research or manual tickets. Historical data integration and any promotion to
executable market-data authority are future Gate 3B work.

## Gate 3B.2 historical foundation

Historical OHLCV is normalized through the project-owned `HistoricalBar` and
`HistoricalBarSeries` contracts. `available_at` is authoritative for
anti-look-ahead; a dated market fact is not proof that an information event was
historically knowable. Raw, adjusted-close and fully-adjusted OHLCV are explicit
and never mixed; adjusted prices cannot feed execution pricing.

Corporate actions use `CorporateActionEvent` plus an append-only
`FirstSeenLedger`. Missing announcement/known-at evidence remains explicitly
uncertified, and first-seen timestamps are assigned at observation time rather
than backdated. Provider disagreements and missing sessions are diagnostics,
not imputation instructions. Gate 3B.2 remains shadow/replay-only.

## Gate 3B.3/3B.4 production evidence and shadow run

Meridian-owned `FundamentalObservation`, `NewsObservation` and
`MacroObservation` contracts keep publication/release, availability and
retrieval timestamps distinct. The SEC adapter is code-only and explicitly
non-PIT-certified; replay evidence is synthetic. No provider observation may
bypass the existing packet, citation, completeness, capability and certified
signal gates.

The bounded `run_shadow_daily` service demonstrates the deterministic pipeline
with a sanitized synthetic account and TEST-mode providers. Its artifacts are
marked `SHADOW / NOT AUTHORIZED FOR ENTRY`; zero certified signals are issued.
Gate 3B.3/3B.4 does not connect live data, brokers or account providers.

## Gate 3B.5 real shadow boundary

Gate 3B.5 adds bounded public Yahoo chart adapters for last-price quotes and
raw OHLCV plus a code-only SEC Company Facts adapter. All observations are
normalized through Meridian contracts and retain provider/timestamp
provenance. Yahoo delay/PIT semantics and SEC filing availability remain
unverified; neither provider is execution-grade.

A real-data shadow run uses a synthetic account and a three-ticker candidate
budget. It does not invoke live TradingAgents or DeepSeek and cannot issue a
CertifiedAgentSignal or manual-entry authorization. Multi-provider evidence is
authorized per cited item through a capability registry, and mixed packet PIT
states never self-upgrade.

## Gate 6F manual decision-support authority

There is exactly one manual-entry authority:

```text
HostAccountSnapshotEnvelope -> normalized AccountSnapshot
  + authoritative SecurityMaster artifact
  + current market/research/risk/reconciliation gates
  + certified ExecutionQuote + capability certificate
  -> ManualReadinessCertificate
  -> build_manual_order_draft -> ManualOrderDraft(NOT_EXECUTED)
```

`MarketSnapshot`, `ResearchMarketPrice`, and `ValuationMark` are disjoint
research/valuation types and cannot authorize manual pricing. `OrderPlanner`,
`attach_limit_prices`, and the legacy compatibility helper emit only
`DRAFT`/diagnostic output. `ManualReadinessCertificate` is the only authority
that can satisfy the seven-gate `MANUAL_ENTRY_READY` transition, and MCP
requires the persisted certificate plus sealed drafts. No draft mutates
holdings or cash; reconciliation observes only a later Host snapshot.

## Historical Gate 6H/6I V1 freeze

`meridian daily` is the one supported daily application path. Development gate
scripts are diagnostic/test-only and delegate to project-owned orchestration;
they do not reimplement alpha arithmetic. Daily packages are sanitized and
append-only under `runs/<date>/<run_id>/`, with separate forward-outcome rows.

TradingAgents and the former DeepSeek lane are retained only as historical or
compatibility notes. The current Astra Skill does not use them as its
intelligence layer. Deterministic code continues to own weights, quantity,
risk, limit policy, and reconciliation. FinRL-X remains optional/deferred and
may remain `MODEL_UNAVAILABLE`.
