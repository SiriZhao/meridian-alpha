# Meridian integration and release closure — Stage B

## Baseline and scope

- Baseline SHA: `0172a00`.
- The user-owned `reports/gate6g-quote-preflight.json` was present and was not
  read, edited, or staged.
- This stage wires existing operational providers, cache and freshness into the
  canonical application daily path.  It adds no broker integration, execution
  capability, alpha model, or LLM authority.

## Code path

```text
python -m meridian daily --snapshot <sanitized-account.json>
  -> MeridianApplicationService.daily
  -> OperationalMarketSnapshotService
  -> OperationalRefreshService (Yahoo primary / Stooq secondary / cache)
  -> bounded Yahoo daily OHLCV enrichment
  -> immutable MarketSnapshot dictionary + cutoff/hash/health
  -> DailyClosureService
  -> deterministic portfolio/risk/reconciliation/order planning
  -> manual-only report under RuntimePaths.reports
```

Configured universe symbols and current holdings form the request set.  Any
missing, stale, future, or conflicting required observation passes an empty
market set to the existing fail-closed closure gate; no partial ticket is
created.  Public observations remain `OPERATIONAL_PUBLIC`, not PIT-certified
research and not execution-grade quotes.  Because public providers do not
supply trusted bid/ask/VWAP, the deterministic limit engine cannot convert a
public result into an executable manual-entry ticket.

`--market-fixture` remains an explicit replay/offline diagnostic mode and the
JSON report labels it `DATA_MODE=FIXTURE`; default daily is
`DATA_MODE=OPERATIONAL_PUBLIC`.

## Provider smoke

At 2026-09-02T13:31Z, the bounded canonical `data-status` and fake-account
daily smoke queried only the configured AAPL/MSFT/NVDA/SPY set. Yahoo returned
invalid public responses and Stooq was unavailable. The run completed in
about 18 seconds and correctly returned `BLOCKED_STALE_MARKET`, with no orders
and `BROKER SUBMISSION = DISABLED`. This is a real degraded/blocking result,
not a provider success claim.

## Verification

- Focused data/daily/application tests: `13 passed`.
- Full suite: `300 passed in 17.91s`.
- `ruff check .`: passed.
- `pyright`: passed.
- `compileall -q src`: passed.
- `git diff --check`: passed.

## Remaining blockers

- Current public provider availability is degraded in this environment.
- Yahoo/Stooq are non-execution-grade: an authorized fresh execution quote is
  still required before a real manual order can become ready.
- Public operational data does not certify historical PIT research.
- The installed `meridian` console-script migration and legacy launcher/MCP
  thin-wrapper work remain Stage A follow-up items; `python -m meridian` is
  the verified canonical entrypoint here.
