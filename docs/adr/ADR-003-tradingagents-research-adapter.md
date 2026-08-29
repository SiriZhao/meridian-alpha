# ADR-003: TradingAgents research adapter boundary

Status: Accepted (Gate 2, DeepSeek research integration)

## Decision

TradingAgents is an optional, isolated dependency. Meridian's mandatory
runtime does not import it. `TradingAgentsResearchEngine` dynamically checks
availability and returns a project-owned `ResearchOutcome`; missing dependency,
credentials, disabled policy, timeout, malformed output, provider failure, and
evidence rejection are explicit statuses, never neutral investment signals.

The adapter accepts only qualitative fields needed for `AgentSignal` and
silently discards shares, target weights, notionals, leverage, order types,
prices, stops, and execution instructions. Deterministic Meridian sizing,
risk, reconciliation, and limit pricing remain authoritative.

Research settings are configurable under `models.yaml: research`, disabled by
default, with bounded retries and bounded parallelism. Batch results are sorted
by ticker. A minimum coverage ratio gates the orchestrator.

LIVE and REPLAY are separate modes. Replay reads sanitized normalized outcomes
only; it never calls a live provider. The replay store records no API keys,
headers, hidden chain-of-thought, or raw vendor transcripts.

Evidence must be structured `EvidenceItem` data with provenance and a
point-in-time timestamp no later than `AgentSignal.as_of`. Live evidence is
marked `LIVE_RESEARCH_OK`; replay fixtures are marked
`HISTORICAL_REPLAY_UNSAFE` unless independently validated.

## LLM provider decision

The current research provider is **DeepSeek**. Meridian uses the official
TauricResearch TradingAgents `deepseek` provider route and the canonical
`DEEPSEEK_API_KEY` environment variable. It does not place a DeepSeek key in
`OPENAI_API_KEY` and does not require an OpenAI account.

- Endpoint: `https://api.deepseek.com` (Meridian does not append `/v1`).
- Development quick/deep model: `deepseek-v4-flash`.
- Future deep role: `deepseek-v4-pro` remains configurable but disabled.
- Thinking/reasoning settings remain policy-controlled; the development
  configuration uses the lowest configured debate depth.

TradingAgents' transport uses an OpenAI-compatible SDK internally, but the
provider identity and endpoint remain explicitly DeepSeek. This is protocol
compatibility, not OpenAI API usage.

## Upstream verification and installation

The official repository was rechecked through its public source on 2026-08-28.
The latest stable release is `v0.3.1`, whose signed tag resolves to commit
`01477f9afb7a47b849ed4c9259d3a9a4738d9fda`. Its `pyproject.toml` declares
Python `>=3.10` and Apache-2.0. The release README and client registry document
`llm_provider = "deepseek"`, `DEEPSEEK_API_KEY`, the
`https://api.deepseek.com` endpoint, and v4 structured tool output. The
official capability table selects function-calling structured output for
`deepseek-v4-flash`/`deepseek-v4-pro` and suppresses unsupported `tool_choice`.

The optional dependency is pinned to the official Git commit with a PEP 508
VCS requirement. The similarly named PyPI wheel was inspected and rejected: it
belongs to an unrelated repository and does not provide the official
`tradingagents.llm_clients` API.

For this Windows environment, Git transport was unavailable, so the exact
official commit archive was downloaded from GitHub codeload and installed from
the extracted source with `pip --no-build-isolation` into `.venv`. The local
install audit recorded:

- Archive: `vendor_cache/TradingAgents-01477f9afb7a47b849ed4c9259d3a9a4738d9fda.zip`
- SHA-256: `6F05AD0D58D3B4634EE574A62224F50AF92ECC91109D7EF9CF253909FDB0468B`
- Verified name/version: `tradingagents` / `0.3.1`
- Verified paths: `tradingagents/graph/trading_graph.py`,
  `tradingagents/default_config.py`, and `tradingagents/llm_clients/`
- License: Apache-2.0

The adapter has two deliberately distinct layers:

1. A client-only structured-output probe (`_official_structured_runner`) is
   retained for adapter contract tests and diagnostics. It is labeled
   `TradingAgentsLLMProbe` and is never selected by the production path.
2. The production path lazily imports the pinned
   `tradingagents.graph.trading_graph.TradingAgentsGraph` and calls
   `propagate`. Its full report state is written only to a temporary,
   project-local directory and deleted after normalization.

The graph's public `propagate` return exposes rendered reports and a
five-tier rating, but not the typed `PortfolioDecision`, numeric conviction,
or source/timestamp evidence. Meridian therefore preserves the rating and
report-presence metadata in a project-owned `GraphResearchSummary` and returns
an `INSUFFICIENT_GROUNDING` outcome without an `AgentSignal`. This is a
successful graph result with insufficient grounding, not malformed provider
output. It never regex-parses the graph's markdown, fabricates conviction, or
treats report prose as EvidenceItem provenance.

Live graph calls are classified `LIVE_RESEARCH_OK` only when `as_of` is within
the configured `research.live_as_of_tolerance_seconds` of the actual run.
Materially historical LIVE calls are rejected with
`HISTORICAL_LIVE_CALL_FORBIDDEN`; historical backtests must use REPLAY fixtures
and never call the live graph. `research.llm_max_retries` controls upstream
LLM retries, while `research.graph_max_retries` controls restarting the whole
graph (example default: zero). The pinned framework has no safe cancellation
hook, so `max_graph_wall_time_seconds` is recorded as an observational limit,
not falsely advertised as enforced cancellation.

Graph execution is bounded by `ResearchBudgetPolicy`, including candidate count,
parallel graph count, maximum graph age, and explicit review of existing
holdings. The intended sequence is deterministic quant pre-screen -> bounded
candidate set -> TradingAgentsGraph -> future grounded normalization; the
pre-screen itself never invokes TradingAgents.

`ResearchEvidencePacket` is the future Meridian-owned grounding contract. Its
bounded EvidenceItems have deterministic stable IDs. A future normalizer must
return direction, research_conviction, thesis, risks, and cited_evidence_ids;
unknown IDs, future evidence, or invented source/timestamp provenance fail
closed.

## Point-in-time and data-provider limits

DeepSeek is an LLM provider, not a market/news/fundamental provider. The
TradingAgents tool graph may use yfinance and other configured vendors; no
additional paid credentials are fabricated. Evidence must still carry source,
timezone-aware timestamp, and type, and timestamps after `as_of` are rejected.
Live vendor results are marked `LIVE_RESEARCH_OK`; replay never invokes a live
LLM and remains `HISTORICAL_REPLAY_UNSAFE` unless separately validated.

The upstream AAPL graph smoke (2026-08-28) completed all four analysts and all
seven high-level report stages. Reddit RSS returned HTTP 429 for `r/stocks` and
`r/investing`; `get_macro_indicators` reported that `FRED_API_KEY` was absent.
These optional vendor gaps were retained as diagnostics. Because the graph
does not return source/timestamp evidence, the result remains unsuitable for
historical replay and cannot become an executable Meridian signal.

## Consequences

A live run is blocked until the official pinned dependency and DeepSeek
credential are present. Once the graph runs, a result still remains
non-executable unless Meridian receives validated conviction and provenance
evidence. Authentication, quota, timeout, rate-limit, model, structured-output,
tool-call, and vendor failures remain explicit provider errors. Exact
token/cost metadata is retained only when a provider exposes it; otherwise it
remains unknown.

The official TradingAgents package may persist its own reports, memory log, and
optional checkpoints under its configured home. Meridian disables checkpoint
persistence, redirects graph persistence to a temporary project-local
directory, and removes it after each run. Meridian never stores private chain
of thought.

## Gate 2.6 correction

The adapter has two distinct layers: a diagnostic TradingAgents LLM-client
structured-output probe and the official `TradingAgentsGraph.propagate`
multi-agent integration. Neither layer alone is Meridian executable research.
Graph output is represented as `GraphResearchSummary`; only a separately
normalized, Meridian-evidence-cited result can cross
`EvidenceAuthorizationService` as `CertifiedAgentSignal`. TEST/REPLAY outputs
are non-executable and the DeepSeek normalizer remains disabled by default.
