# Meridian Alpha — Gate 3B.3 Production Evidence Foundation

## Scope and status

Gate 3B.3 adds Meridian-owned contracts for fundamental, news and macro
observations. It does not promote any provider to executable authority. All
new production-facing adapters remain shadow/research-only until their
availability and point-in-time semantics are independently certified.

## Fundamentals

`FundamentalObservation` keeps filing identity/type, period end, value/units,
publication time, `available_at`, retrieval time and source provenance. The SEC
Company Facts adapter is code-only in this gate. It uses public SEC endpoints,
requires no API key, and deliberately declares `supports_point_in_time=false`
and `research_grade=false`: a current filing response cannot prove what was
known at an historical cutoff. A fiscal period end is never used as the
availability timestamp.

## News

`NewsObservation` requires a stable document identity, headline, source,
entity/ticker links, publication time, availability time, retrieval time and a
content hash. Publication must not be later than availability, and ambiguous or
missing timestamps are rejected. The packet builder deduplicates by Meridian's
stable provenance ID; syndicated variants remain separately inspectable unless
their normalized identity is equal.

## Macro

`MacroObservation` models an observation period separately from release time,
revision and retrieval time. Without vintage/release certification its PIT state
is `UNVERIFIED`; modern revised values cannot be used as historical knowledge.

## Authorization boundary

Observations enter the existing `EvidencePacketBuilder`, citation validator,
provider-capability checks and `CertifiedAgentSignal` boundary. Synthetic and
replay observations are explicitly marked and cannot become executable
research. Provider failures are recorded per provider and do not create a
neutral or guessed signal. TradingAgents graph summaries remain qualitative
context only; they do not provide Meridian evidence provenance.

## Offline validation

The Gate 3B.3 tests cover timezone and publication ordering, stable provenance,
synthetic replay providers, and non-network behavior. No SEC, news, macro,
DeepSeek or TradingAgents live request was made in this gate. The only
available evidence fixtures are synthetic/replay and therefore remain
non-executable.

## Remaining issues

- SEC filing acceptance/publication-time and historical availability need a
  supervised, independently certified ingestion design.
- News publication/availability and syndicated-article reconciliation require a
  future provider review.
- Macro vintage/revision semantics are not certified.
- No paid provider or broker is connected.
