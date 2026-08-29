# ADR-004: Research evidence and grounded normalization

Status: Accepted (Night Phase Part 2, offline foundation)

## Context

TradingAgentsGraph produces useful finalized reports and a qualitative rating,
but the graph result does not itself prove Meridian provenance, point-in-time
availability, or numeric conviction. A graph rating is therefore not an
investment signal and must not enter Alpha Fusion or order generation.

## Decisions

- Meridian owns EvidenceItem, ResearchEvidencePacket, and the citation
  validator. Evidence IDs are deterministic hashes of normalized provenance.
- GroundedResearchRequest contains only a bounded GraphResearchSummary and a
  Meridian-owned packet. It never contains credentials, account numbers,
  authorization headers, hidden chain-of-thought, or full private transcripts.
- GroundedResearchSignal requires an explicit Decimal conviction in [0, 1],
  direction, thesis, risks, and packet-resolving cited evidence IDs. No
  Buy/Hold/Sell-to-conviction mapping exists.
- AgentSignal creation is a gate after status, identity, timestamp, citation,
  and point-in-time checks. Empty, unverified, future, or replay-unsafe
  evidence cannot authorize production executable research. TEST fixtures may
  opt into synthetic conversion, but remain marked synthetic and non-production.
- The DeepSeek normalizer is a code-only, structured-output adapter disabled by
  default. It receives only bounded ticker/as-of context and Meridian evidence IDs
  (graph rating and reports are not executable inputs) and cannot invent URLs,
  timestamps, evidence, sizing, prices, or execution actions.
- Graph summaries, evidence packets, and grounded signals replay as separate
  versioned artifacts with created_at, as_of, provider metadata, and content
  hashes. Historical backtests use replay and never fall back to live LLM or
  current web/news/macro sources.
- Audit metadata may retain candidate decisions, graph status/rating, evidence
  IDs, provider statuses, grounded status, model metadata, warnings, and
  duration. Hidden reasoning and raw transcripts are never persisted.

## Consequences

Successful graph work can be reviewed without being misrepresented as a
grounded Meridian recommendation. A later supervised gate must supply
independently validated, provenance-bearing providers and explicitly review the
normalization policy before executable-path research is enabled.
