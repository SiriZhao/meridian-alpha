# ADR-006 — Production Evidence Foundation (Gate 3B.3/3B.4)

## Decision

Meridian owns the domain contracts for fundamentals, news and macro evidence.
Adapters normalize provider responses into provenance-bearing observations with
separate publication/release, `available_at` and retrieval timestamps. The
existing EvidencePacketBuilder, citation validator, provider capability checks
and CertifiedAgentSignal boundary remain mandatory.

The SEC Company Facts adapter is code-only until historical filing availability
is independently certified. News and macro providers are replay/synthetic in
this gate. A bounded TEST shadow daily run demonstrates composition but emits
zero executable research authorization and is marked `SHADOW / NOT AUTHORIZED
FOR ENTRY`.

## Rationale

A current API response is not evidence that an information event was available
at an historical decision cutoff. Keeping provider types outside domain models
and requiring Meridian-owned provenance prevents accidental look-ahead and
vendor semantics from entering Alpha Fusion.

## Consequences

- Provider failures are isolated and explicit; no neutral signal is fabricated.
- Synthetic/replay evidence remains non-executable.
- Future live promotion requires supervised PIT, capability and licensing
  review; no broker or account integration is implied.
