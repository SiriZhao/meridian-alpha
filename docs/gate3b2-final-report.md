# Meridian Alpha — Gate 3B.2 Final Report

## Status

- Historical OHLCV: implemented as `HistoricalBar`/`HistoricalBarSeries` with
  identity, calendar, OHLCV, currency, timestamp, provenance, quality and
  certification checks.
- Raw/adjusted contract: `RAW`, `ADJUSTED_CLOSE` and
  `FULLY_ADJUSTED_OHLCV` are explicit; adjusted prices are never execution
  eligible.
- Corporate actions: split, dividends, symbol changes, delisting, merger and
  acquisition types plus known-at certification and reconciliation diagnostics.
- First-seen ledger: append-only, payload-hashed, clock-assigned timestamps;
  no backdating.
- Historical PIT: market-session facts and information-event availability are
  separate. Missing known-at evidence remains uncertified.
- Data quality: missing/duplicate sessions, zero volume, invalid OHLC,
  adjustment and provider disagreement diagnostics are explicit; no silent
  imputation.
- Golden dataset: bounded synthetic fixture coverage for AAPL, MSFT, NVDA, SPY, QQQ, GLD, SGOV and VIX
  US instruments; no large frozen dataset and no live historical download.
- Shadow features: deterministic feature output includes cutoff, sessions and
  input hash; promotion is disabled.

## Validation

- `pytest`: 129 passed
- `ruff`: passed
- `pyright`: passed
- `git diff --check`: passed
- Safe review package: `artifacts/meridian-alpha-gate3b2-review.zip` (111 paths,
  0 forbidden paths)

## Safety

No broker, Schwab, FinRL-X, live order or execution capability was added. No
live API or paid provider was called during Gate 3B.2. Historical work remains
SHADOW/REPLAY-only.

## Known P1 issues

- No independently certified live historical provider is connected.
- Corporate-action historical known-at certification still requires a future
  supervised provider and provenance review.
- Public quote-provider availability/timestamp semantics from Gate 3B.1 remain
  unresolved.

Gate 3B.3/3B.4 was subsequently added as a shadow-only evidence foundation and deterministic daily run.



