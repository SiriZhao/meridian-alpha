# Astra read-only research boundary

Date: 2026-09-11. Status: accepted for final review.

The Astra-facing MCP surface provides evidence and deterministic calculations.
The legacy `run_daily_analysis` and `run_host_daily_analysis` Python functions
remain compatibility entry points but are no longer registered MCP tools:
the latter writes audit state and can invoke a nested Codex research pipeline.
Labeling those operations read-only was inaccurate. Paper and canonical daily
operation remain explicit CLI workflows with their existing safety gates.

`research_packet` accepts a symbol and cutoff as an alternative to a supplied
validated package. It composes existing market and certified SEC services and
performs no LLM call. Missing news, macro and valuation remain explicit unknowns.
No broker capability, new provider framework, or execution authority is added.

Tool receipt time is reported separately from source known-at time. Missing
source availability timestamps remain null. Caller-supplied bars are labeled
unverified; deterministic arithmetic does not certify their provenance.
