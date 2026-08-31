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

## Gate 6A production architecture

The authoritative decision path is `real quant -> CertifiedEvidenceView ->
DeepSeek grounded research -> EvidenceAuthorizationService ->
CertifiedAgentSignal -> AlphaFusion -> deterministic allocator -> RiskEngine ->
reconciliation`. TradingAgents is qualitative second-opinion/context only; it
does not supply the production grounded signal. DeepSeek may affect research
alpha only. Deterministic code owns weights, cash, risk, quantities, and prices.
FinRL-X remains an optional isolated challenger and is not promoted.

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

## Gate 3B.1 shadow market data

Gate 3B.1 introduces a provider-independent Security Master and quote contract.
Unknown symbols, wrong provider mappings, future/stale timestamps, currency
mismatches and inverted markets fail closed. Public quote observations are
explicitly SHADOW and cannot create executable research, allocation or manual
order readiness. Bid/ask is never inferred from a last price.

## Gate 3B.2 historical data

Historical market rows and corporate actions carry separate event, observed,
available and retrieved timestamps. `available_at` controls look-ahead. Raw and
adjusted prices are never conflated, and adjusted prices cannot be used for
manual order pricing. Historical fixtures remain SHADOW/REPLAY-only and cannot
authorize executable research or orders.

## Gate 3B.3/3B.4 evidence and shadow status

Fundamental, news and macro observations are Meridian-owned and carry explicit
publication/release, available and retrieval times. Current SEC Company Facts
integration is code-only and not historical-PIT certified. Replay fixtures are
synthetic and cannot authorize executable research.

The Gate 3B.4 daily exercise is a bounded TEST/shadow run over a synthetic
account. It reports graph context and evidence diagnostics separately and
always emits `SHADOW / NOT AUTHORIZED FOR ENTRY`; no real account, broker,
DeepSeek or TradingAgents call is made.

## Gate 3B.5 real shadow data

Real public market and SEC observations may be displayed in a bounded shadow
run, but remain `UNVERIFIED`/non-executable until provider capability and
point-in-time certification pass. Quotes are last-only where bid/ask is absent;
adjusted or stale data cannot authorize execution. The shadow account is
synthetic and output remains `SHADOW / NOT AUTHORIZED FOR ENTRY`.

## Gate 4F/4G identity and quote semantics

Legal security identity is promoted only from a hashed HTTPS primary source
(SEC for issuers, official sponsor/exchange documentation for ETFs, and Cboe
for VIX), with an explicit historical effective interval. Provider symbol
mappings are separate and cannot promote identity. The development fixture
registry remains non-authoritative until a caller explicitly loads a captured
certificate set.

Host input is accepted only as a sanitized `HostAccountSnapshotEnvelope`; the
shared normalization path rejects sensitive keys and emits explicit account,
security, market, research, quote, risk, reconciliation, and manual-entry
gates. No supplied Host envelope means `READY_FOR_SUPERVISED_HOST_INPUT`.

`ExecutionQuote` is a distinct type from research prices and valuation marks.
Manual-ticket pricing requires a provider capability certificate proving bid,
ask, last, timestamp/session, freshness, identity, licensing, and rate-limit
semantics. Yahoo remains last-only research data and `TO_BE_SELECTED` providers
cannot authorize a manual ticket. A draft is always `NOT_EXECUTED`.
