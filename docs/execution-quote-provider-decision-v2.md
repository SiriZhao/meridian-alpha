# Execution quote provider decision v2

Status: **TO_BE_SELECTED**. This Gate performed read-only provider research;
it did not connect to Schwab, a broker, an account, or an order surface.

| Candidate | Bid/ask | Timestamp/session | Coverage | Licensing/auth | Decision |
| --- | --- | --- | --- | --- | --- |
| Yahoo chart | No dependable bid/ask | Delay and session semantics unverified | Research shadow only | Public use/rate limits need review | Rejected for ticket pricing |
| Licensed consolidated market-data vendor | Candidate only | Must prove exchange timestamp, freshness and extended-hours semantics | US equities/ETFs; verify VIX scope | Contract and credentials required | Not connected |
| Exchange/CBOE-authorized feed | Candidate only | Must prove source, session and stale-quote behavior | Venue-specific | Licensing required | Not connected |

## Certification gate

A future read-only adapter needs a capability certificate proving all of:

- bid, ask, last, currency, timezone-aware timestamp, and session state;
- documented freshness semantics and bounded error/rate-limit behavior;
- stocks, ETFs, and a separately verified VIX/index posture;
- licensing and permitted manual-ticket use.

Returning bid/ask alone is insufficient. Missing bid/ask, inverted market,
wide spread, stale/future timestamp, wrong currency/ticker, after-hours, and
provider failure must all fail closed. Yahoo remains a research market price;
