# TRADINGAGENTS_UPGRADE_ASSESSMENT — 2026-09-16

## Current integration

Meridian retains a lazy, optional adapter pinned to TradingAgents v0.3.1 commit
`01477f9afb7a47b849ed4c9259d3a9a4738d9fda`. It is not a base dependency, is
not installed by the canonical runtime, and is explicitly disabled for normal
production research. Injected runners and replay fixtures cover the boundary;
graph prose/rating cannot produce Meridian quantity, price, risk authority, or
paper fills.

## Upstream access result

Upstream verification was attempted with `git ls-remote` and GitHub HTTP/API
requests. All attempts failed in the current host context: Git reported
`SEC_E_NO_CREDENTIALS`, and HTTP/API requests returned transport errors. The
repository contains only the previously cached/pinned v0.3.1 evidence. Therefore
the current latest release, commit history, breaking changes, and license state
after v0.3.1 are **not verified in this audit**. No upgrade claim is inferred
from memory or stale documentation.

## Compatibility and cost

- The locally reviewed v0.3.1 material uses a materially heavier optional
  LangChain/LangGraph/provider dependency surface than Meridian's base runtime.
- Meridian's adapter targets v0.3.1 module/config behavior and rejects a version
  mismatch. A direct bump would require adapter, graph-state, checkpoint,
  provider, persistence and latency re-certification.
- Enabling the graph would materially increase cold start, installation size,
  network/provider variability and multi-agent latency. Historical Meridian
  evidence already recorded an approximately 705-second graph observation.

## Decision

**DEFER / DO NOT SYNC.** Upstream changes could not be verified, the adapter is
not used by the canonical path, and a blind bump would violate the controlled
upgrade requirement. Meridian's project-owned data and Host consistency layers
remain authoritative. No vendor code, dependency, or lockfile was changed.

Reconsider only if Meridian defines a bounded research experiment with a
measurable quality target, isolated environment, pinned commit, latency budget,
provenance normalization, and proof that TradingAgents remains optional and
cannot reach allocation, risk, execution planning, paper accounting, or any
broker write.
