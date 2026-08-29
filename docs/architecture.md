# Architecture

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
Manual Order Ticket (human enters it at Schwab)
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
7. Emit `READY_FOR_MANUAL_ENTRY` only if every required gate passes; otherwise
   fail closed as analysis-only, draft, or blocked.

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

## Gate 2 research boundary

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

## Intended future research pipeline

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
