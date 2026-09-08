# ADR-011: Resource-aware research universes

Status: Accepted

## Context

The canonical daily path previously sent every eligible market observation to
the advisory research stage. If that set exceeded
`max_graph_tickers_per_run`, the stage correctly rejected the request, but a
single extra symbol could block all research even when a bounded subset was
safe to process.

## Decision

Canonical daily now creates three nested, deterministic layers before provider
invocation:

- **eligible universe**: symbols with validated, fresh canonical market inputs;
- **research universe**: the policy-bounded pool ranked by required holding
  review and current dollar volume;
- **deep analysis universe**: the resource-bounded subset actually disclosed to
  the advisory provider.

The configured research budget remains a hard maximum. A coarse local resource
profile may lower that maximum but never raise it. If the eligible set is too
large, the scheduler records `mode=reduced`, selects the highest-liquidity names
deterministically, and continues through the existing canonical research
request. Required holding review still fails closed if local capacity cannot
cover every required holding.

Reports and JSON expose the original, research, and deep-analysis counts, the
full/reduced mode, the policy/resource limits, and the selection basis. Resource
metadata contains only CPU count and coarse physical memory; it carries no host
identity or secret.

## Consequences

`RESEARCH_UNIVERSE_BUDGET_EXCEEDED` remains a provider-side defense in depth,
but normal oversized universes are reduced before reaching it. The scheduler
does not calculate signals, target weights, quantities, limit prices, gates, or
execution authority. LONG ONLY, manual confirmation, advisory-only LLM output,
paper-only execution, and disabled broker submission remain unchanged.
