# Meridian Alpha — Gate 6H / 6I final report

## Status

`V1_BLOCKED_ON_EXTERNAL_INPUT` and `V1_READY_FOR_SHADOW_OBSERVATION`.
The v1 code feature set is complete for safe daily shadow observation. This is
not a manual-entry or execution release.

## Production path

The supported command is `meridian daily`. It uses the shared
`DailyOrchestrator` and packages a sanitized run under
`runs/<date>/<run_id>/`. The path is:

`AccountSnapshot -> deterministic quant -> certified/replay research -> AlphaFusion -> allocator -> risk -> reconciliation -> shadow ledger/report`.

Quant/LLM attribution is recorded as unavailable/`INSUFFICIENT_SAMPLE` when
production alpha rows are not present; no portfolio-weight arithmetic is used
to manufacture attribution.

## Observation controls

- Profiles: `TEST`, `REPLAY`, `SHADOW_LIVE`, `MANUAL_DECISION_SUPPORT`.
- `SHADOW_LIVE` requires explicit opt-in; historical replay is cache/frozen only.
- The offline battery completed 200 cycles with zero network calls.
- Recommendation, target, simulated outcome, and brokerage truth are separate.
- Forward outcomes remain pending until their availability time.
- System health is conservative; unavailable quote capability is a safety-critical blocker.

## Release blockers

- External: no externally authorized real Host snapshot has been supplied.
- External: no certified read-only ExecutionQuote capability certificate exists.
- Observation: the minimum completed-session observation period has not elapsed.

FinRL-X is `MODEL_UNAVAILABLE`/optional post-v1. TradingAgents is qualitative
second-opinion context only. DeepSeek certified evidence is the production
research path. News and macro remain context-only unless separately PIT-certified.

## Safety

`BROKER: NONE`; `SCHWAB: NOT CONNECTED`; `REAL ORDERS: ZERO`; no execution,
broker login, order write, cancellation, or automatic model promotion occurred.
Known P0: **0**. Known P1: real Host input, certified quote, and observation
period.

## Final status print

```text
MERIDIAN ALPHA — V1 CONVERGENCE STATUS
PRODUCTION ALPHA: IMPLEMENTED / SHADOW
FIVE-EQUITY FUNDAMENTALS: AAPL MSFT NVDA META GOOGL (baseline artifacts)
CERTIFIED LLM: replay/frozen outputs where valid
DISLOCATION: SHADOW / observation only
SECURITY MASTER: 11/11 authoritative when explicit artifact is loaded
MANUAL AUTHORITY: CONVERGED
HOST REAL SMOKE: NOT AVAILABLE
EXECUTION QUOTE: NOT CERTIFIED
MANUAL ENTRY READY: NO
DAILY APP: meridian daily
SKILL/MCP: read-only surface
SHADOW LEDGER: append-only
ATTRIBUTION: INSUFFICIENT_SAMPLE when rows unavailable
SYSTEM HEALTH: RED when quote capability is unavailable
SOAK: 200 cycles, zero network calls
FINRL-X: DEFERRED / optional
SCHWAB: NOT CONNECTED
BROKER: NONE
REAL ORDERS: ZERO
CODE BLOCKERS: NONE KNOWN
EXTERNAL BLOCKERS: REAL_HOST_INPUT, EXECUTION_QUOTE_CERTIFICATION
OBSERVATION BLOCKERS: MINIMUM_COMPLETED_SHADOW_SESSIONS
KNOWN P0: 0
```
