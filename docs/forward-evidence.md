# Forward Evidence Factory

Forward evidence is an append-only shadow-evaluation record. It never changes
allocation, risk limits, manual authority, paper-fill eligibility, or strategy
promotion.

## Canonical flow

```text
canonical daily result
→ freeze per-symbol prediction
→ wait for configured NYSE-session maturity
→ ingest outcome only from the canonical market observation
→ append immutable outcome
→ shadow-only evaluation
```

Only canonical daily may freeze a prediction. The factory consumes the final
decision, selected market snapshots, cutoff, policy/model hashes and a
sanitized account reference. It does not fetch a second quote, recompute target
weights, or accept fixture runs as forward evidence.

`policies/forward_evidence.yaml` defines benchmark, required sample count and
trading-session horizons. Current horizons are `SHORT` (5 sessions) and
`MEDIUM` (20 sessions). Weekends, major US exchange holidays and DST are handled
through the shared NYSE calendar; an outcome cannot be appended before the
maturity session's close.

Each prediction records its authority key, daily run ID, information cutoff,
trading session, maturity session, universe, benchmark inception price, mode,
policy/model/market hashes, signal, target weight and exposure. A second
identical freeze is idempotent. A different prediction for the same account,
session, symbol, horizon, policy and mode is rejected as
`FORWARD_AUTHORITATIVE_PREDICTION_CONFLICT`.

## Modes and evidence boundary

The contract can record `PURE_QUANT`, `QUANT_PLUS_PROBABILITY`,
`QUANT_PLUS_LLM`, `QUANT_PLUS_PROBABILITY_PLUS_LLM`, and
`FULL_INTELLIGENCE_ADAPTIVE_EXPOSURE`. Canonical daily currently freezes only
`PURE_QUANT` or `QUANT_PLUS_LLM` when its existing advisory research actually
validated. Unsupported/missing probability or adaptive components are not
fabricated and do not increase influence.

Public operational market data remains operational, not PIT-certified research
or a certified execution quote. `EVALUABLE_SHADOW_ONLY` and
`NOT_ELIGIBLE_AUTOMATIC_PROMOTION_DISABLED` explicitly prohibit promotion.
Until the configured mature sample count is reached, the status includes
`maturity_status = NOT_MATURE`.

## Operator commands

```powershell
.\scriptsun_meridian.ps1 forward-status --json
.\scriptsun_meridian.ps1 paper run --account Schwab-Paper --json
```

The paper command carries the canonical daily `forward_evidence` object into
its JSON and Markdown report. A blocked market, fixture, stale account or
failed decision yields `FORWARD_NOT_FROZEN`; it never creates a substitute
prediction.
