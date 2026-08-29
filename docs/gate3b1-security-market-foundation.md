# Gate 3B.1 — Security Master and Shadow Market Foundation

## Status

Implemented offline contracts and a conservative public shadow adapter. Real
observations are diagnostic only and cannot authorize `CertifiedAgentSignal`,
allocation, `READY_FOR_MANUAL_ENTRY`, or broker activity.

## Security Master

`meridian.security_master.SecurityMaster` owns canonical identity. The initial
verified fixture distinguishes AAPL, MSFT, NVDA, SPY, QQQ, SGOV, GLD, TLT and
the CBOE index identity `VIX` (provider symbol `^VIX` for Yahoo and `^vix` for
Stooq). Unknown symbols and missing provider mappings fail with
`SECURITY_IDENTITY_UNAVAILABLE`. Conflicts downgrade a record to
`CONFLICTING`; no source is silently preferred.

## Calendar

`meridian.trading_calendar` uses timezone-aware `America/New_York` sessions,
weekend/holiday rules, DST-safe open/close conversion, and a separate CBOE VIX
close policy. `latest_completed_session` requires a regular close to have
passed; the calendar date alone is never treated as complete.

## Quote contract

`QuoteObservation` carries canonical identity, provider symbol, observed and
available timestamps, retrieval time, last/bid/ask, currency, market status,
provenance and quality. Missing bid or ask is explicitly
`BID_ASK_UNAVAILABLE`; no spread is manufactured from last. All timestamps,
prices, currency and bid/ask ordering are validated by `QuoteNormalizer`.

## Boundary

`ShadowMarketDataPolicy` mechanically reports that `REAL_SHADOW_MARKET_DATA`
cannot authorize executable research. The Stooq public CSV adapter is
last-price-only, delayed/semantics-limited, and marked
`execution_quote_grade=false`. A single successful request is not provider
certification.


## Shadow smoke observation (2026-08-29)

A seven-symbol request (AAPL, MSFT, NVDA, SPY, QQQ, SGOV, VIX) was attempted
against the public endpoint with an eight-second timeout. Every request failed
at the network boundary (`QuoteProviderError`); no quote was accepted and no
fallback or fabricated value was used. This is an environment/network
availability observation, not provider certification.
