# Operational data plane

Operational data answers whether Meridian can run a bounded analysis today.
It is distinct from research/PIT certification and cannot upgrade historical
constituents, corporate actions, SEC facts, survivorship, or execution quotes.

`OperationalRefreshService` is the single intended data boundary: primary
provider → secondary provider → provenance-preserving cache → immutable
snapshot. Its observations have a symbol, last price, market timestamp,
received time, provider, source type, currency, session, quality, and content
hash. Future observations are rejected. A provider failure, HTML/malformed
response, empty result, or timeout is explicitly unavailable/invalid rather
than a synthetic quote.

Run the additive status command through the Windows launcher:

```powershell
.\scripts\run_meridian.ps1 data-status --json
```

It reports `OPERATIONAL_READY` separately from `RESEARCH_BLOCKED` and always
states `OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH`. Existing public Yahoo and
Stooq adapters remain shadow/last-price sources and cannot authorize orders or
manual entry. The bounded default command makes no network call; refresh must
be explicitly requested through the future daily integration boundary.
