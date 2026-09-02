# Advisory intelligence and Dip Scout

Meridian keeps deterministic quant/risk/order logic separate from structured
event intelligence. `ResearchPacket` has a strict cutoff and provenance for
every evidence item. Malformed, timed-out, absent, or mismatched provider
output becomes `RESEARCH_UNAVAILABLE`; it never becomes a guessed opinion.

The default intelligence mode is advisory/shadow. A research opinion can say
`BUY_RESEARCH`, but it has no order authority. Deterministic risk can return
`BLOCK_ADD`, in which case the synthesized output is `WATCH_NO_ORDER`.

`DipScout` is a configurable-universe candidate assessment, not a fixed
portfolio or a buy instruction. It combines drawdown, trend, volatility, quant
score, portfolio concentration and structured thesis-damage assessment into
`STRONG_CANDIDATE`, `CANDIDATE`, `WATCH`, `AVOID`, or `INSUFFICIENT_DATA`.

Forward predictions and mature outcomes live in an append-only ledger. Fewer
than 20 mature observations reports `INSUFFICIENT_FORWARD_EVIDENCE`; no alpha
claim or model promotion is permitted.
