# TradingAgents capability assimilation

Upstream baseline: TradingAgents `v0.5.0`, commit `2d17df8`, released
`2026-09-18`.

Meridian absorbs selected correctness capabilities from TradingAgents v0.5.0;
it does not transfer framework ownership. TradingAgents is not a runtime
dependency, its LangGraph hierarchy is not copied, and it has no access to the
paper ledger, allocation, risk, order construction or broker boundary.

## Authority boundary

GPT may analyze a frozen evidence packet, immutable portfolio snapshot and
verified market references. It may return structured research and advisory
price proposals. Deterministic Meridian code alone owns freshness, evidence
eligibility, portfolio sizing, quantities, limits, risk, reconciliation and
manual-entry readiness. A model cannot mutate a ledger or submit an order.

## Point in time

`ResearchTemporalContext` is created once at the runtime boundary and carries
the run ID, trading date, as-of time, information cutoff, market session,
timezone and optional portfolio snapshot identity. Research inputs must match
that cutoff. Evidence carries observation, publication, effective, availability
and retrieval semantics where known. Future observations or availability are
rejected. Research cache identity includes the exact as-of instant, preventing
a current cache entry from being reused as a historical vintage.

Sources that cannot establish historical availability remain unavailable or
unverified; present-day data is never relabelled as historical evidence.

## SEC as filed

The native SEC lane uses official ticker, Company Facts and submissions
metadata endpoints. Facts are joined to exact accessions and SEC acceptance
timestamps. Eligibility requires `accepted_at <= information_cutoff`; later
amendments and restatements therefore cannot leak into an earlier run. Network
calls have a bounded timeout/retry budget and optional atomic cache. Transport
failure is `SEC_COMPANYFACTS_UNAVAILABLE`, not “no fundamentals.”

## Portfolio snapshot

The paper ledger or supplied account snapshot is transformed into a frozen
`PortfolioSnapshot`. Missing context is represented by absence, never by an
invented flat book. GPT receives only a read-only serialized view. The snapshot
has no fill, ledger or execution methods and cannot grant trading authority.

## Decision and price integrity

Schema failures become `REVIEW_REQUIRED`; timeouts remain `LLM_TIMEOUT`;
insufficient or stale evidence remains non-tradeable. `NO_ACTION` is accepted
only from a schema-valid research response. A `GroundedPriceProposal` binds its
reference price to a market timestamp and evidence IDs. Deterministic policy
sets maximum age and returns `PRICE_PROPOSAL_STALE` after expiry.

## Historical evaluation isolation

`ResearchBacktestRunner` evaluates independent symbol/date cells with a
historical temporal context. It writes only under `<chosen-root>/backtests/<run-id>`:
decision JSONL, calibration JSONL and a summary. Resume skips completed cells.
It does not model fills or transaction assumptions and has no canonical
database or paper-ledger dependency.
