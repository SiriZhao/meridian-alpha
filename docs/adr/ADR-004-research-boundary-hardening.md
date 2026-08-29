# ADR-004: Research boundary hardening

Status: Accepted (Gate 2.5)

## Context

TradingAgentsGraph can complete its multi-agent workflow while exposing only
rendered reports and a rating. Those outputs are useful research context, but
they do not carry the Meridian provenance and numeric conviction required for
an executable AgentSignal. Live graph calls also receive a calendar trade date
upstream, so they cannot be treated as arbitrary historical, point-in-time
queries.

## Decisions

- A successful graph is represented by `GraphResearchSummary` and an
  `INSUFFICIENT_GROUNDING` `ResearchOutcome`. It is never `AVAILABLE` and never
  supplies conviction, shares, weights, prices, leverage, stops, or broker
  actions.
- `LIVE_RESEARCH_OK` requires `as_of` to be within the configurable
  `research.live_as_of_tolerance_seconds` of the actual invocation. Materially
  historical LIVE calls fail closed as `HISTORICAL_LIVE_CALL_FORBIDDEN`.
  Historical backtests use REPLAY fixtures only.
- `llm_max_retries` and `graph_max_retries` are independent. The development
  graph retry default is zero, so a late graph failure does not restart the
  whole workflow. `max_graph_wall_time_seconds` is observational because the
  pinned framework does not expose safe cancellation.
- `ResearchBudgetPolicy` deterministically bounds graph candidate count and
  parallelism and can require existing holdings to be reviewed. The
  deterministic pre-screen precedes graph invocation.
- `ResearchEvidencePacket` defines the future Meridian-owned grounding input.
  Evidence IDs are deterministic; cited IDs must resolve to the packet. No
  production normalizer or live evidence provider is enabled in this gate.
- Review archives are created only by `scripts/package_review.ps1`, which
  excludes secret environment files, credentials, caches, virtual environments,
  vendor cache, runtime state, and databases.

## Consequences

Graph ratings remain visible for diagnostics without being mistaken for a
validated investment signal. Until a later grounded-normalization gate supplies
Meridian EvidenceItems and an explicitly reviewed conviction policy, the graph
cannot authorize Alpha Fusion or manual-order output.
