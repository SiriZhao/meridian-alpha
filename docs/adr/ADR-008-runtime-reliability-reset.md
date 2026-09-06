# ADR-008 — canonical runtime and live cutoff

Status: accepted for Reliability Reset, 2026-09-07.

The installed entrypoint `meridian.application_cli:main` is the canonical local
application boundary. Windows launcher and Skill delegate to it. Existing
RuntimePaths owns mutable state; wheel resources contain read-only policies.
Daily initializes the existing SQLite v1 schema and records sanitized decisions.
No broker, sizing, pricing, risk or manual-approval authority is added.

Fixed-time replay continues rejecting observations received after its cutoff.
Explicit live retrieval sets its analysis cutoff after receipt, never before
the network request. Otherwise every live observation is rejected merely for
arriving after the invocation start. Provider timestamps and freshness remain
validated; stale quotes do not become executable prices.

Runtime completion and research/manual readiness are separate. The current
canonical research component is NOT_RUN and drafts are research-only. Missing
certified evidence is not disguised as successful LLM analysis.
