# ADR-005: Candidate screening and research budget

Status: Accepted (Night Phase Part 2, offline foundation)

## Context

The recorded AAPL TradingAgentsGraph observation took approximately 705 seconds.
Running that multi-agent graph across an entire universe is therefore
unbounded in cost and latency and is not an acceptable default.

## Decisions

- Deterministic quant features and a CandidateSelector run before any graph.
  The pre-screen never calls an LLM and never fabricates fundamentals, news, or
  macro facts.
- Candidate priority is required existing-holding review, highest available
  quant score, explicit risk-triggered names, then deterministic ticker order.
- ResearchBudgetPolicy enforces max_graph_tickers_per_run and
  max_parallel_graphs before graph invocation. Development defaults are three
  tickers and one graph in flight.
- Candidates below minimum_quant_score are deferred unless required for holding
  review or promoted by an explicit risk flag. Deferred candidates and reasons
  are returned, not silently discarded.
- always_review_existing_holdings and existing_holding_review_policy are
  explicit configuration. If the budget cannot cover required holdings, the
  candidate set fails closed.
- max_graph_age_hours is reserved for future sanitized graph-cache reuse. Until
  that cache has an integrity and freshness design, no graph result is reused.

## Consequences

Research becomes a bounded deep-research stage rather than a universe scanner.
Quant-only screening remains deterministic and testable. The tradeoff is that
deferred names receive no graph context in the current run and must be
explicitly surfaced for a later run.
