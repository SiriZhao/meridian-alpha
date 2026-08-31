# V1 release blockers

| Category | Blocker | State | Owner/next proof |
|---|---|---|---|
| CODE | Core daily path, sealed manual authority, replay/shadow ledger | CLOSED | Regression suite |
| EXTERNAL | Authorized sanitized Host account snapshot | OPEN | Host supplies a fresh envelope; run `meridian host-smoke <file>` |
| EXTERNAL | Certified read-only ExecutionQuote provider | OPEN | Provider semantics, feed, timestamp, freshness, session and licensing proof |
| OBSERVATION | Completed shadow sessions | OPEN | Human-reviewed operational observation period |

No blocker may be bypassed by a fixture, stale quote, research mark, or
`MarketSnapshot`. Manual readiness requires all seven gates and a certified
ExecutionQuote capability certificate.
