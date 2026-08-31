# Build state — Gate 2 (DeepSeek provider)

> Historical Gate 2 notes below are retained for provenance. Current Gate 6A
> status: TradingAgents is qualitative context only; DeepSeek grounded research
> consumes certified evidence; production AlphaFusion, allocation, risk, and
> reconciliation are shadow-only. No broker/Schwab surface exists.

## Gate 2.5 - Research boundary hardening

- Successful TradingAgents graphs now produce a project-owned
  `GraphResearchSummary` and `GRAPH_SUMMARY_ONLY` outcome rather than an
  invalid-signal error.
- Live graph calls enforce configurable as-of tolerance; replay cannot invoke
  a live graph.
- LLM retries and whole-graph retries are separate. Development graph retry
  default is zero, and v0.3.1 wall-time cancellation is documented as
  unavailable.
- `ResearchBudgetPolicy` bounds graph candidates and parallelism.
- `max_graph_age_hours` is available for future graph-cache reuse; the current
  adapter does not reuse graph cache, so no stale cache can silently enter a
  decision.
- `ResearchEvidencePacket` and grounded-normalization contracts are defined but
  no production evidence provider is connected.
- `CandidateSelector` performs a deterministic, quant-only pre-screen,
  prioritizes required holding reviews, enforces `minimum_quant_score`, and
  exposes deferred candidates. Development graph budget is capped at three
  tickers with one graph in flight.
- Meridian-owned evidence protocols, synthetic replay providers, stable
  provenance IDs, packet bounds, and completeness diagnostics are implemented.
  Synthetic packets are explicitly marked `HISTORICAL_REPLAY_UNSAFE` and cannot
  authorize executable research.
- `scripts/package_review.ps1` creates a source review archive without secrets,
  caches, virtual environments, vendor cache, or databases.

**State:** project constitution, deterministic core, and isolated TradingAgents
research boundary are implemented. No live trading or brokerage workflow is
enabled.

## Workspace decision

The supplied workspace already contains unrelated, uncommitted projects. This
project therefore lives in the isolated `meridian-alpha/` subdirectory. No
existing workspace file is modified.

## Python decision

**Selected version: Python 3.12.**

| Upstream | Reviewed state | Python declaration | Decision |
| --- | --- | --- | --- |
| TradingAgents | v0.3.1; `01477f9afb7a47b849ed4c9259d3a9a4738d9fda` | `>=3.10`; upstream uses 3.12 | Compatible |
| FinRL-X / FinRL-Trading | v2.0.2 metadata; `e65d6f0483ead7d2ef4a5fc940cdf960392a25c1` | `>=3.11`; classifiers 3.11/3.12 | Compatible |

Review date: 2026-08-28. Public source metadata may advance; revalidate the
specific commit immediately before enabling either adapter.

## Dependency and license assessment

Both reviewed repositories declare Apache-2.0, which is compatible with using
them as separately installed optional dependencies, subject to normal NOTICE /
attribution review at distribution time. Meridian Alpha does not vendor either
codebase.

Their full dependency graphs overlap substantially (`pandas`, `pydantic`,
`requests`, `yfinance`) but have materially different optional heavy stacks:
TradingAgents brings LangChain/LangGraph and multiple model-provider packages;
FinRL-X brings ML, visualization, backtest, and an Alpaca-capable execution
stack. Installing both into Meridian's base environment would enlarge the
trusted surface and introduce resolver risk.

Strategy: the base project uses only narrow core dependencies. `tradingagents`
and `finrlx` extras are independently pinned (including commit evidence) and
loaded only by their adapters. The TradingAgents extra uses the official
TauricResearch VCS commit; the similarly named PyPI wheel was rejected as an
unrelated MIT project. FinRL-X execution-related modules
must never be imported by Meridian.

## Integration decisions

- **TradingAgents:** optional research-only adapter using native DeepSeek
  provider routing (`DEEPSEEK_API_KEY`, `https://api.deepseek.com`,
  `deepseek-v4-flash` development model). The production path invokes the
  official `TradingAgentsGraph.propagate` multi-agent workflow. Its rating and
  report-presence metadata remain non-executable diagnostics because the public
  return does not expose Meridian conviction or provenance-bearing evidence;
  client-only structured probing is test/diagnostic-only. Any sizing,
  execution, or price instruction is discarded.
- **FinRL-X:** optional allocator adapter, usable only with a validated,
  versioned model artifact suitable for the configured universe. Otherwise it
  reports `MODEL_UNAVAILABLE` and Meridian uses its deterministic fallback.
- **OpenAI/ChatGPT:** future tool-only MCP boundary, with a thin bridge if one
  is useful. The Python quantitative core remains Python.

## Risks discovered

1. FinRL-X contains live/paper Alpaca execution components; its dependency and
   import boundary must be tightly isolated and audited before use.
2. TradingAgents is LLM-driven and intentionally nondeterministic; it must be
   research-only and record model/provider/date/version metadata.
3. Both upstream repositories and public data providers can change. Pinning,
   regression tests, provenance, and freshness/no-look-ahead gates are required.
4. The project uses Python 3.12 in `.venv`; the `uv` executable is not
   available in this environment, so validation uses the equivalent
   `.venv\Scripts\python.exe -m ...` commands.
5. Neither upstream project makes a validated, universal pretrained FinRL-X
   allocator artifact available for this product contract; no model output may
   be claimed until one is independently validated.

## References reviewed

- [OpenAI Developers — Plugins](https://developers.openai.com/plugins)
- [TradingAgents repository](https://github.com/TauricResearch/TradingAgents)
- [FinRL-X / FinRL-Trading repository](https://github.com/AI4Finance-Foundation/FinRL-Trading)

## Gate 2 state

 The project-owned TradingAgents adapter, real `TradingAgentsGraph.propagate`
boundary, bounded batch interface, and sanitized replay store are implemented.
The official release/tag/commit, Python requirement, DeepSeek provider,
structured-output capability, data-vendor behavior, checkpoint behavior, and
Apache-2.0 license were reverified from upstream. A single AAPL graph smoke
completed with all seven high-level report fields present; Reddit RSS returned
HTTP 429 and FRED was unavailable without `FRED_API_KEY`. Meridian preserves
that graph result as non-executable because conviction and EvidenceItem
provenance are not exposed. No Schwab, FinRL-X, production market-data, or
brokerage capability is connected.

The local `.env.local` file is git-ignored. Its value is never printed or
persisted by Meridian. Live smoke testing is attempted only with an explicit
`--live` command; ordinary pytest remains offline.

## Night Phase Part 2 state

Night Phase Part 2 is complete as an offline/replay-first foundation. The
project now has explicit `GroundedResearchRequest`,
`GroundedResearchSignal`, and `GroundedResearchOutcome` contracts,
citation-gated `AgentSignal` creation, and a code-only
`DeepSeekGroundedResearchNormalizer` that defaults to `live_enabled: false`.
Graph summaries, Meridian evidence packets, and grounded signals remain
separate replay artifacts with schema versions and content hashes.

`ResearchPipelineService` is the single TEST/REPLAY/LIVE research boundary.
Candidate selection is deterministic and budgeted before any graph provider;
the development budget is three graph tickers and one graph in flight. TEST
uses clearly marked synthetic fixtures, REPLAY loads only validated recorded
artifacts, and disabled LIVE returns `LIVE_RESEARCH_DISABLED` without a
network call. No live provider was used in this phase.

Meridian-owned `EvidenceItem` provenance, stable IDs,
`ResearchEvidencePacket`, bounded fake/replay providers, and completeness
diagnostics are implemented. A graph rating alone remains qualitative context;
without explicit conviction and packet-resolving evidence the result is
`GRAPH_SUMMARY_ONLY`/`INSUFFICIENT_GROUNDING`, never an executable
`AgentSignal`. Audit and reporting expose candidate, graph, evidence, and
grounding status without secrets, account data, hidden reasoning, or full
transcripts.

The safe review packager writes only source-review paths and excludes env files,
credentials, VCS metadata, environments, vendor cache, runtime state, logs,
caches, and databases. Part 2 does not start Gate 3B and does not connect
DeepSeek, TradingAgents live graphs, Schwab, FinRL-X, production market data,
or brokerage execution.
## Gate 2.6 safety convergence status

IMPLEMENTED/TESTED: cumulative projected portfolio validation, closed PIT
allowlist, mandatory authoritative availability for certification, certified
research boundary, provider capability enforcement, bounded deterministic
candidate selection, synchronized-account readiness, and offline mode
isolation.

NOT CONNECTED: live DeepSeek/TradingAgents, production evidence providers,
Schwab, FinRL-X execution, and broker writes. Gate 3B remains blocked pending
supervised production evidence/PIT certification.

## Gate 3B.1 status

Implemented and tested: durable Gate 2.6 baseline commit, project-owned
Security Master, US/CBOE calendar semantics, quote normalization, typed market
capabilities, provider disagreement diagnostics, and a public Stooq SHADOW
adapter. No historical provider, broker, or executable market-data authority
is connected. The real-network smoke was attempted only in SHADOW mode and is
blocked by the current environment's public-network failure.

## Gate 3B.2 status

Implemented and tested: project-owned historical OHLCV contracts, raw/adjusted
semantics, deterministic quality/reconciliation diagnostics, corporate-action
events, first-seen ledger and shadow feature lineage. No historical or paid
provider is connected; no historical information-event PIT certification or
execution authorization is enabled.

## Gate 3B.3/3B.4 status

IMPLEMENTED/TESTED: project-owned fundamental/news/macro observation contracts,
per-provider failure isolation, SEC adapter code-only boundary, and bounded
synthetic shadow daily pipeline with candidate diagnostics.

SHADOW/NOT CONNECTED: SEC historical PIT certification, news publication and
syndication certification, macro vintage/revision certification, live grounded
normalizer, live TradingAgents and all broker/account integrations. The shadow
run issues zero `CertifiedAgentSignal` objects and cannot authorize entry.

## Gate 3B.5 status

IMPLEMENTED/TESTED: clock-relative TradingAgents tests, per-provider evidence
capability registry, conservative packet PIT aggregation, public Yahoo quote /
raw OHLCV shadow adapters, SEC Company Facts shadow ingestion, network
preflight metadata, and bounded real-data shadow reports.

NOT CERTIFIED: authoritative Security Master provenance, Yahoo delay/PIT and
licensing semantics, SEC filing acceptance-time PIT, news publication/availability,
and macro vintage semantics. No live DeepSeek/TradingAgents, broker, Schwab,
account or FinRL-X integration is enabled.

## Gate 6D/6E current state

Implemented/tested: append-only sanitized shadow and outcome ledgers, replay
battery, bounded 100-cycle offline soak, typed provider health, deterministic
system health, explicit non-execution profiles, Chinese mobile report V3,
operator runbooks, and future-only broker boundary design.

Current blockers are honest: no real Host smoke, no execution quote certificate,
and no isolated FinRL-X runtime or OOS-validated artifact. Production remains
on the deterministic allocator; no automatic promotion, broker write, Schwab
authentication, or real order exists.
