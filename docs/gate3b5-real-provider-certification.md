# Meridian Alpha — Gate 3B.5 Real Provider Certification

## Certification posture

Gate 3B.5 exercised public data adapters with bounded real requests. The
observations are valid SHADOW inputs, not executable authorization. Provider
capabilities are recorded in `reports/gate3b5-provider-certification.json`.
Unknown or unverified capabilities remain false.

## Network preflight

A strict five-second HTTPS preflight was run against four public endpoints:

- SEC `data.sec.gov`: HTTP 200, TLS/DNS successful.
- Stooq CSV endpoint: HTTP 404 after reaching the host; it remains diagnostic
  only.
- BBC Business RSS (news candidate): HTTP 200; no Meridian news adapter was
  promoted because historical publication/availability semantics were not
  certified.
- FRED landing page (macro candidate): HTTP 200; no vintage-aware adapter was
  promoted.

Preflight proves reachability only. It does not certify licensing, freshness,
or point-in-time availability.

## Real market provider

`YahooChartQuoteProvider` and `YahooChartHistoricalProvider` normalize public
Yahoo chart responses into Meridian `QuoteObservation` and
`HistoricalBarSeries` contracts. Provider symbols are resolved through the
Security Master, timestamps are timezone-aware, raw OHLCV is preserved, null
rows are treated as missing sessions, and malformed/future/identity-invalid
rows fail closed.

The observed quote fields were last-only. Bid and ask were not manufactured;
quality is `BID_ASK_UNAVAILABLE` or `STALE` as appropriate, and
`execution_quote_grade=false`. Yahoo's delay and historical availability
semantics are not independently certified, so `supports_point_in_time=false`
and `research_grade=false` remain in force.

## SEC fundamentals

`SECCompanyFactsProvider` successfully participates in the real shadow packet
when the endpoint returns data. It preserves CIK/accession/document identity,
filing type, period end, filed timestamp and retrieval timestamp. SEC Company
Facts `filed` date is not treated as a defensible acceptance/publication time;
`supports_point_in_time=false`, and observations remain `UNVERIFIED`.

## Evidence authorization

Packets with mixed providers are authorized through a provider-name capability
registry. Each cited item must resolve to its own certificate, satisfy provider
PIT/research-grade claims, and pass `available_at`, citation and completeness
gates. An unknown provider or capability mismatch fails closed. Packet status
only becomes certified for homogeneous explicit item certification; `VERIFIED`,
`RECENT`, mixed and unverified observations do not upgrade to historical PIT.

## Not connected

No real news or macro evidence adapter, DeepSeek normalizer, live TradingAgents
graph, Schwab/account source, FinRL-X module or broker surface was invoked.
