# Gate 3B.2 — Point-in-Time Historical Market Data

## Implemented

`meridian.historical.HistoricalBar` is the project-owned historical OHLCV
contract. Each row carries canonical identity, provider symbol, exchange
session/calendar, raw-or-adjusted semantics, currency, observed/available/
retrieved timestamps, provenance, quality and certification. Identity,
timezone, currency, OHLC ordering, non-negative volume and valid trading
session are validated before a row enters a series.

`available_at` is the anti-look-ahead authority. A row whose session or
availability is after the requested cutoff is rejected. Missing sessions are
reported, not forward-filled. Duplicate sessions and provider disagreements
are explicit diagnostics; conflicting values are never averaged.

## Two distinct historical claims

1. **HISTORICAL MARKET FACT** — an exchange-session OHLCV row for a dated
   session, with a provider timestamp and normalized identity.
2. **HISTORICAL INFORMATION AVAILABILITY** — proof that an information event
   (for example a corporate action) was knowable by a cutoff. A current API
   returning an old price does not prove this second claim.

The current fixtures are replay/synthetic shadow data. They are not certified
for executable research or order pricing. No real historical provider is
connected in this gate.

## Raw versus adjusted

`RAW` prices preserve the reported market session and are the only prices that
could be considered for future execution-quote workflows. `ADJUSTED_CLOSE`
and `FULLY_ADJUSTED_OHLCV` are explicitly labeled for quantitative research or
total-return analysis only. An adjusted value can never be used as an
execution price, and raw and adjusted series must not be mixed implicitly.

## Shadow features

`generate_shadow_features` applies existing deterministic feature functions to
bars available by a cutoff and returns a content hash plus session lineage.
The result is replay/shadow metadata and is not automatically promoted to
executable market data.


## Golden validation universe

`meridian.golden_dataset` defines a bounded synthetic validation universe:
AAPL, MSFT, NVDA, SPY, QQQ, GLD, SGOV and VIX. It is deliberately small and
marked synthetic; split/dividend boundary examples are represented by separate
corporate-action fixtures rather than a large frozen price database.
