# Failure / safety evaluation matrix

| Category | Case | Expected result |
| --- | --- | --- |
| Account | no account / missing holdings | `ACCOUNT_DATA_UNAVAILABLE` or blocked |
| Account | $0 balance | `NO_CAPITAL`, no orders |
| Account | stale snapshot / partial fill / manual trade | use current snapshot only; never infer fill |
| Market | missing/stale quote, wide spread, gap, outage | draft or `BLOCKED_STALE_MARKET` |
| AI | timeout, malformed output, contradiction, rate limit | ticker failure isolated; no fabricated signal |
| Allocator | FinRL-X unavailable/invalid artifact | deterministic fallback |
| Orders | insufficient cash, oversell, tiny/duplicate order | no invalid draft |
| System | retry, duplicate run id, corrupt cache | idempotent audit or fail closed |

The current pytest suite covers the zero-capital, stale-account, no-look-ahead,
cash-budget, and leverage-disabled cases. The remaining rows require a verified
data integration and expanded property/evaluation suite before release.
