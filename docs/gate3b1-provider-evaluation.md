# Gate 3B.1 — Provider Evaluation

## Implemented provider

The development adapter is `StooqQuoteProvider`, a small standard-library
HTTP/CSV boundary. It requires no API key and returns a normalized last-price
observation. It does not claim historical point-in-time, bid/ask, adjusted
data, corporate-action, or execution-quote capabilities. Timestamp semantics
are the provider's quote date/time and local freshness is measured at receipt.

The adapter is network-capable only when explicitly constructed and is never
used by TEST or REPLAY. It is suitable for SHADOW diagnostics, not for
executable decisions.

## Capability evaluation

| Capability | Stooq public CSV | Gate 3B.1 interpretation |
|---|---|---|
| Live / last | Last endpoint response; live semantics unverified | Shadow observation only |
| Historical PIT | Unverified | Not authorized |
| Bid / ask | Not supplied | `BID_ASK_UNAVAILABLE` |
| Currency | Normalized to Security Master | Mismatch rejects row |
| Authentication | None | No secret required |
| Research grade | Unverified | Not authorized until independently certified |
| Execution quote grade | No | Cannot price or authorize orders |

Provider terms, rate limits and timestamp completeness require confirmation
before any production use. No paid provider is selected in this gate. A future
provider must publish a typed capability certificate and pass the same identity,
timestamp, stale-age and disagreement tests.


## Network result

The Gate 3B.1 public shadow smoke was attempted for the representative universe
but the current environment could not complete any Stooq request. The failure
is recorded explicitly; no credentials were read, no data was fabricated and
no executable path consumed the provider.

