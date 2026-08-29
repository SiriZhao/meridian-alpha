# Historical Data Certification

## Certification levels

- `CERTIFIED_MARKET_SESSION`: normalized exchange-session fact with verified
  identity, valid calendar session, timestamps and OHLCV constraints.
- `UNVERIFIED`: normalized observation whose historical provider semantics are
  not independently certified.
- `SYNTHETIC` / `REPLAY_UNSAFE`: offline fixtures that cannot authorize an
  executable path.
- `NOT_CERTIFIED_FOR_HISTORICAL_INFORMATION_EVENT`: explicit state for an
  event lacking reliable known-at/announcement evidence.

Market-session certification and information-event availability are separate
contracts. A dated OHLCV row may be a valid historical market fact while a
split or dividend record for the same date remains unavailable for a
point-in-time backtest.

## Anti-look-ahead requirements

Every executable candidate must satisfy `available_at <= cutoff`; naive or
future timestamps are rejected. Current/incomplete sessions are excluded by
the project-owned calendar. Invalid gaps remain missing unless a future,
explicitly reviewed policy authorizes an imputation method. Adjusted prices
are never used for execution pricing.

## Current status

Gate 3B.2 provides deterministic offline normalization, reconciliation,
quality diagnostics and shadow feature lineage. It does not connect a live or
historical paid provider, does not certify corporate-action historical
availability, and does not authorize orders. Public provider selection and
supervised historical validation remain future work.

