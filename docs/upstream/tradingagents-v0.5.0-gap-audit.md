# TradingAgents v0.5.0 assimilation gap audit

- Audit date: `2026-09-19`
- Upstream: `TauricResearch/TradingAgents`
- Release: `v0.5.0`
- Release commit: `2d17df8da1536c121e4d7395ac5a5dcec9e96d6f`
- Release date: `2026-09-18`

The upstream checkout was obtained read-only under `.tmp/TradingAgents-v0.5.0`.
It is gitignored and is not a Meridian dependency or runtime input. This audit
uses the tag, not `main`.

## Inspected upstream implementation and tests

Implementation reviewed: `CHANGELOG.md`, `tradingagents/dataflows/date_window.py`,
`tradingagents/dataflows/sec_edgar.py`, `tradingagents/dataflows/y_finance.py`,
`tradingagents/dataflows/fred.py`, `tradingagents/dataflows/news_data.py`,
`tradingagents/portfolio.py`, `tradingagents/backtest.py`,
`tradingagents/graph/trading_graph.py`, `tradingagents/graph/propagation.py`,
`tradingagents/graph/signal_processing.py`, `tradingagents/agents/utils/rating.py`,
`tradingagents/agents/utils/memory.py`, `tradingagents/reporting.py`, and the
LLM client retry/configuration code.

Tests reviewed: `test_sec_edgar.py`, `test_fundamentals_lookahead.py`,
`test_tool_date_enforcement.py`, `test_undated_tools_as_of.py`,
`test_news_lookahead.py`, `test_social_lookahead.py`, `test_memory_pointintime.py`,
`test_portfolio_context.py`, `test_backtest.py`, `test_reporting.py`,
`test_llm_max_retries.py`, `test_market_data_validator.py`,
`test_cli_decision_log.py`, and `test_structured_agents.py`.

Material v0.5.0 behavior verified in code includes: graph-state date injection
for dated tools; EDGAR facts selected by `filed <= curr_date`, including
amendments; optional portfolio context kept distinct from a flat book; a
`REVIEW` rating for unreadable decisions; a separate backtest decision log and
holding-period settlement; vendor failures/unavailable feeds represented as
errors or sentinels; provider retry budgets; and technical/trader prompts that
include reported prices. The release also contains a full LangGraph hierarchy,
provider SDK surface, and optional memory system.

## Meridian audit

Inspected Meridian files: `src/meridian/daily_research.py`,
`src/meridian/codex_provider.py`, `src/meridian/gpt_native_research.py`,
`src/meridian/data/models.py`, `src/meridian/schemas.py`, `src/meridian/evidence.py`,
`src/meridian/fundamentals.py`, `src/meridian/orchestrator.py`,
`src/meridian/application.py`, `src/meridian/research_stage.py`,
`src/meridian/runtime.py`, `src/meridian/runtime_diagnostics.py`,
`src/meridian/daily_closure.py`, `src/meridian/mcp_server.py`, and the
existing TradingAgents adapter/replay boundary. Tests include the canonical,
provider-fallback, evidence, historical, Codex, native GPT, paper-runtime and
runtime-database suites.

### Already Present / `ALREADY_SUPERIOR`

- Meridian has project-owned evidence authorization, deterministic allocation,
  quote certification, risk/reconciliation/manual-entry gates, and a hard
  broker-disabled boundary. TradingAgents cannot supply these authorities.
- `DailyResearchInput.analysis_cutoff`, `EvidenceItem.available_at`, PIT
  certification, historical fundamental filtering, and strict evidence citation
  checks already reject many future facts.
- Portfolio/account data is sanitized and excluded from persistent Codex packet
  hashes and reports by design; this is safer than a generic portfolio prompt.
- Native research already has explicit `TIMEOUT`, `SCHEMA_ERROR`, unavailable
  stages, bounded budgets and deterministic downstream decision states.

### Adapted / `ADAPT`

- Canonical and live-advisory research inputs now receive an immutable temporal
  context, and retrieval/cache boundaries validate exact temporal identity.
- Evidence now expresses publication, effective and availability times.
- Codex/native decisions distinguish schema review and timeout from investment
  `NO_ACTION`.
- A Meridian-native isolated ticker/date evaluation runner writes decision and
  calibration JSONL without touching the paper ledger.

### Implemented / `ASSIMILATE`

1. Temporal context propagation for canonical research, shadow research and
   live advisory, plus future-data and fallback rejection.
2. SEC as-filed accession/acceptance-time certification with bounded transport,
   cache and explicit unavailable semantics.
3. Frozen portfolio snapshots and evidence-grounded expiring price proposals.
4. Isolated historical decision/calibration logs with resume and summary.

### Deferred

- CLI exposure for the evaluation runner and exchange-calendar filtering.
- Broader non-SEC alternative-data certification where providers cannot yet
  establish historical availability.
- Return-by-confidence-bucket and benchmark/drawdown reporting; these require
  approved historical outcome sources and must not invent fills or costs.

### Explicitly rejected / `REJECT`

- Direct TradingAgents dependency, vendor copy, LangGraph hierarchy, or agent
  graph adoption.
- TradingAgents portfolio manager as a sizing or price authority.
- Upstream memory/checkpoint persistence in the canonical ledger.
- Any broker login, order submission, fill inference, or live execution path.

## Batch 1 foundation implemented

- `ResearchTemporalContext` (`run_id`, trading date, `as_of`, information
  cutoff, session, timezone and optional portfolio snapshot identity) is now an
  immutable contract. `DailyResearchInput` validates matching cutoffs and
  `ResearchPacket` propagates the canonical cutoff.
- `EvidenceRecord` now supports nullable `published_at`, `effective_at` and
  `available_at`; publication/effective/availability after the research cutoff
  is rejected while `retrieved_at` remains a retrieval-time audit fact.
- `ResearchFailureStatus` and Codex diagnostic `failure_status` distinguish
  valid output, review, insufficient/stale evidence, schema failure, timeout,
  unavailable LLM and unavailable data. Existing `NO_ACTION` output remains
  reserved for a schema-valid provider response.

## Compatibility and migration risks

The new fields are optional and therefore preserve existing fixtures and the
canonical database schema. No runtime migration was run. Future callers should
construct the temporal context at the runtime boundary and pass it through;
providers must not synthesize a different cutoff. Persisting raw account
context remains prohibited.

## Required tests and final status

Implemented coverage includes context propagation, cutoff mismatch and
future-data rejection, availability semantics, SEC filing/restatement isolation,
portfolio snapshot immutability, explicit decision failure classification,
grounded-price staleness, replay resume/calibration determinism, and existing
Codex/paper regressions. Remaining provider breadth and CLI exposure stay
deferred; they are not prerequisites for this assimilation boundary.
