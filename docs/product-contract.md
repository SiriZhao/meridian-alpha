# Product contract

## What Meridian Alpha does

Given a newly supplied, sanitized `AccountSnapshot` and time-verified market
data, Meridian Alpha can analyze a defined US-equity universe and prepare a
target portfolio plus a human-readable manual limit-order ticket.

## What it never does

- It never authenticates to, reads from, or writes to the Schwab Trading API.
- It never submits, places, executes, or cancels a brokerage order.
- It never assumes a previous recommendation filled.
- It never fabricates missing account, market, model, or evidence data.
- It never presents executable orders when required account or market freshness
  is unknown or stale.

## Truth and freshness

Only the current `AccountSnapshot` establishes cash and holdings. A prior
recommendation is audit context only. A daily run begins with a new snapshot;
if it is absent, stale, or unverifiable, the outcome is blocked rather than a
guessed portfolio.

Market facts used in an executable path must include a timestamp and provider
provenance. Historical analyses must be point-in-time and no-look-ahead.

## Decision ownership

LLMs may provide qualitative research, narration, and evidence interpretation.
Deterministic, policy-controlled code alone determines target sizing, risk
constraints, share quantities, and limit-price calculations. A human reviews
and manually enters every real order.

## Privacy

The default audit record is sanitized metadata, decision hashes, warnings,
target weights, and drafts. It does not persist raw snapshots, brokerage account
numbers, secrets, or tokens.

## Status semantics

- `NO_CAPITAL`: account fact is valid but deployable capital is zero; no orders.
- `ANALYSIS_ONLY` / `DRAFT`: analysis may be useful but cannot be entered.
- `READY_FOR_MANUAL_ENTRY`: all required gates passed; still not executed.
- `BLOCKED_*` / `FAILED`: fail closed; no executable ticket.

## Gate 1.5 status semantics

NO_ACTION is the safe terminal state when the target already matches current positions and no order is required. READY_FOR_MANUAL_ENTRY always contains at least one priced order; it never means executed.

## Gate 2 research semantics

Research outcomes are explicit (`AVAILABLE`, `INSUFFICIENT_GROUNDING`,
`UNAVAILABLE`, `TIMEOUT`, `INVALID_OUTPUT`, `REJECTED_EVIDENCE`, or
`PROVIDER_ERROR`) and are never represented as a
neutral opinion. The current provider is DeepSeek, configured with
`DEEPSEEK_API_KEY`; OpenAI credentials are not required. Live research is only
enabled by an explicit `--live` request; incomplete research produces a
non-executable draft. The live adapter invokes the official
TradingAgentsGraph.propagate multi-agent workflow. Its five-tier rating is
preserved for diagnostics, but without validated numeric conviction and
timestamped provenance it cannot become an AgentSignal or executable research
result. Exact token/cost values are reported only when exposed by the
provider.

The successful graph summary uses `GRAPH_SUMMARY_ONLY`; a later grounding failure uses `INSUFFICIENT_GROUNDING`, distinct from
`INVALID_OUTPUT` and `PROVIDER_ERROR`; it can never become an AVAILABLE
AgentSignal through Alpha Fusion. Live graph calls are point-in-time safe only
within `research.live_as_of_tolerance_seconds`. Historical work uses REPLAY
fixtures exclusively and never falls back to a live graph or current vendor
data.

`GRAPH_SUMMARY_ONLY` is an equivalent diagnostic semantic for a completed
graph whose finalized reports are available but whose Meridian evidence and
conviction contract is not satisfied. Neither status authorizes Alpha Fusion,
allocation, or executable output.

Grounded research is a separate contract: GroundedResearchSignal must carry an
explicit numeric conviction and packet-resolving evidence IDs. The
EvidenceCitationValidator rejects unknown, future, cross-ticker, unverified,
or replay-unsafe citations on the executable path. TEST may opt into synthetic
fixtures for offline E2E, but those outputs remain explicitly synthetic and
cannot be treated as production research.

## Gate 2.6 certification boundary

A graph result is qualitative context (`GRAPH_SUMMARY_ONLY`) until Meridian-owned
EvidenceItems are normalized and authorized. `CertifiedAgentSignal` is issued
only by the evidence authorization service after citation, PIT, provider
capability, completeness, and timestamp checks. Synthetic and replay artifacts
cannot authorize executable research. TEST and REPLAY are non-network modes;
LIVE requires explicit policy enablement. This gate does not connect production
data providers or brokers.
