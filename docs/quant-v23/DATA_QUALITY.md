# Data evidence audit

| Level | Permitted conclusion | Current coverage |
|---|---|---|
| CERTIFIED_PIT | Qualified chronological financial evaluation, subject to additional universe/actions checks | No new qualified real history supplied |
| PUBLIC_EXPLORATORY | Latest-vintage descriptive price/factor/reference statistics with assumptions | Yahoo SPY/QQQM/AAPL/MSFT/NVDA, source hashes and actual retrieval times |
| SYNTHETIC_DIAGNOSTIC | Timing, constraints, costs, determinism and engineering regressions | Existing 420-session six-symbol fixture, unchanged |
| MISSING_EVIDENCE | Explicit blocker; no estimated price/return/confidence substitution | Historical availability, survivor/delistings, PIT sectors/fundamentals, observed spread |

Public chart endpoint is accessed without cookies, credentials or login. Rights
to redistribution/commercial use have NOT been independently verified. Raw
responses and immutable receipts stay in isolated `.tmp` cache, not Git.
Checked-in summary contains derived statistics and public source fingerprints.
Network calls are bounded (15s, 10 MB); no retries or silent provider substitution.

Coverage requested 2019-01-01 through 2025-12-31. QQQM begins 2020-10-13 in the
provider response; it is not backfilled before inception. Comparison reference
window was fixed at 2021-01-01 through 2025-12-31 for all five symbols. Current
configured AAPL/MSFT/NVDA plus references are surviving assets, NOT reconstructed
historical investable membership. Historical sector / ETF look-through remains
unknown. No sector guesses, broad-market breadth, delisted returns or fundamentals.

OHLC and adjusted close are distinct fields. Latest adjusted-close ratios are
used ONLY as an assumed retrospective total-return proxy in public reference
statistics. Event receipts include reported dividends/splits/capital gains;
coverage completeness, revision vintage, adjustment conventions and ex-date
cash treatment are not independently certified. Nonpositive/inconsistent OHLC,
missing adjustment, incomplete split ratio, future events, identity mismatches,
duplicate/reversed timestamps and non-finite values are rejected. Missing volume
remains null. Missing price rows are recorded, never filled. Extreme adjusted
return >50% requires review. This gate does not prove all smaller errors absent.

`historical_available_at=null` is a type-level requirement. Retrieval time is
preserved and never reinterpreted as historical availability. Public data are
never passed to strict FeatureSnapshot/PIT replay by inventing old timestamps,
certification or a synthetic label. Execution certification remains false.

The provider session grid is observed, not a certified historical calendar.
An important real exception: [NYSE's announced closure on 2025-01-09](https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx).
The repository's reviewed calendar scope is 2026–2028 (ADR0035); older routine
calendar assumptions must not force-fill this date. Public rows align exactly
to SPY; metrics disclose observed grid, 252 volatility convention and actual
calendar-year CAGR. This is insufficient for a certified historical strategy run.

Strict financial V2.3 comparison requires independently reviewed adjusted OHLCV,
availability/revision evidence, corporate-action cash/share handling, historical
membership and metadata, delistings and an independently reviewed exchange
calendar. No adapter or engineering test supplies these missing facts.
