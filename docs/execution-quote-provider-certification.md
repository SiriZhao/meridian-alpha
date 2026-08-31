# Gate 4G execution-quote provider certification

Status: **TO_BE_SELECTED**. No provider is execution-certified in this
checkpoint. Meridian did not connect Schwab, a broker, an account, or an order
surface. Gate 6C adds read-only candidate adapters and `meridian
quote-preflight`; a reachable endpoint is still insufficient for certification.

## Candidate review

| Candidate | Bid/ask | Timestamp and session | Coverage | Auth/rate limits | Licensing/manual-ticket posture | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Polygon.io Stocks WebSocket/REST | Quote and trade endpoints document bid/ask fields for supported feeds | Exchange/event timestamps and regular versus extended session must be proven in the selected plan | US stocks/ETFs; VIX/index coverage is separate and unproven | API key and plan limits required; no key configured | Plan terms and redistribution/manual-ticket use require contract review | Candidate only |
| Alpaca Market Data API | Latest quote exposes bid/ask/last for supported symbols | Quote timestamps and feed/session semantics are documented per feed but require account-plan verification | US equities/ETFs; VIX/index posture not proven | API credentials and subscription/limits required | Terms and permitted manual-ticket use require review | Candidate only |
| Yahoo chart | Last/regular-market price only in Meridian's adapter; no dependable bid/ask | Delay, exchange timestamp, and after-hours semantics are not certified | Research shadow only | Public endpoint/rate limits and terms are unverified | Not suitable for manual ticket pricing | **Rejected** |

The provider-neutral `ExecutionQuoteProvider` boundary has two optional,
read-only candidate adapters: `AlpacaExecutionQuoteProvider` and
`PolygonExecutionQuoteProvider`. They require local credentials to make a
bounded probe, never expose those credentials in output, and advertise
`execution_quote_grade=false` until the selected plan/feed is reviewed.

## Certification gate

Before a candidate can be marked `execution_quote_grade=true`, a supervised
read-only configuration must prove all of the following for AAPL, NVDA, and
SPY (and separately document VIX/index handling):

1. bid, ask, last, symbol identity, USD currency, and timezone-aware event
   timestamps are returned from the documented endpoint;
2. the timestamp is an exchange/provider observation time, not merely retrieval
   time, and the provider's delay or real-time status is known;
3. regular, pre-market, after-hours, closed, and halted-session semantics are
   explicit; unsupported extended-hours observations fail closed;
4. stale, future, missing, inverted, and excessively wide markets are rejected
   by Meridian's pure validator;
5. authentication, bounded rate limits, data licensing, and the intended
   human-manual-ticket use are documented for the selected plan.

No API key or provider configuration was available for this gate. Therefore no
read-only adapter was connected, no quote capability certificate was issued,
and `MANUAL_ENTRY_READY = NO` remains the only valid status. Yahoo remains a
`ResearchMarketPrice` source and cannot be converted into an
`ExecutionQuote`.

## Gate 6G supervised review (2026-08-31)

The provider-neutral preflight was run in configuration-only mode for the
bounded read-only candidates. No local Alpaca or Polygon credentials were
configured, so no network probe was attempted and no capability certificate
was issued. The adapter source documentation remains the following official
references (reviewed 2026-08-31):

- Alpaca latest stock quotes/trades: <https://docs.alpaca.markets/reference/stocklatestquotes-1>
- Polygon v3 stock quotes: <https://polygon.io/docs/stocks/get_v3_quotes__stockticker>

For both candidates, the selected plan/feed, real-time or delay entitlement,
exchange-event timestamp semantics, session/halt behavior, rate limits, and
licensing/manual-ticket posture remain **UNVERIFIED** until an authorized plan
review and bounded read-only probe establish them. Missing licensing terms are
not inferred. VIX/index coverage is separate and is not covered by an
AAPL/NVDA/SPY equity/ETF result. `execution_quote_grade` therefore remains
false and manual-entry readiness remains blocked.