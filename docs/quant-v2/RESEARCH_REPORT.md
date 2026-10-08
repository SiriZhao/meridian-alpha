# Quant Engine V2 research and delivery evidence

Decision: **ALPHA_NOT_YET_DEMONSTRATED**. The engine is implemented and the
diagnostic registry completed; verified financial OOS evidence is absent.
Paper-candidate status is **INSUFFICIENT_EVIDENCE**, with no promotion.

## Information set and factor definitions

Features use at most 253 contiguous, completed US-equity sessions. Every row
must have observed/available times no later than the decision cutoff, matching
identity and currency, positive OHLC, verified adjustment basis and certified
provenance. Future rows are excluded; missing sessions are rejected, never
filled. Zero or unavailable volume produces an explicit missing factor.
Each factor records name/version, symbol, cutoff, lookback, raw/normalized
value, lineage/content hash, availability, quality and missing reason.

For closing price P[t], momentum(h)=P[t]/P[t-h]-1 at h=21,63,126,252.
12-1 momentum=P[t-21]/P[t-252]-1. Relative momentum subtracts aligned SPY
126-session return; risk-adjusted momentum divides by annualized 60-session
volatility. These are trading-session proxies, not an exact implementation of
the French portfolio construction ([primary definition](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html)).

Trend includes SMA20/60/200, price/SMA200-1, SMA60[t]/SMA60[t-20]-1,
positive-return fraction over 60 sessions and distance from the 60-session high.
Risk features include sample return standard deviation times sqrt(252),
20/60-session volatility, downside RMS times sqrt(252), ATR14, maximum trailing
60/252-session peak-to-trough drawdown, aligned relative volatility and
60-session beta/correlation with explicit zero-variance handling.
Liquidity is mean(price*volume) over 20 sessions. Volatility percentile ranks
the current 20-session volatility against rolling 20-session windows within
the trailing 252 returns. Five-session reversal is diagnostic only.
No valuation, financial statement, guessed sector or current index membership
is backfilled into history. Extra computed factors are exposed for inspection;
they are not arbitrarily summed into the production score.

## Frozen mathematical score and risk interpretation

For at least five valid cross-sectional observations and nonconstant values,
each factor uses tied midranks: z=2*(below+(ties-1)/2)/(N-1)-1. Otherwise
z=x/(abs(x)+scale), with declared scales 0.10 for momentum and 0.05 for trend.
u=(z+1)/2. Ranks provide bounded outlier robustness without fitting means,
standard deviations or winsorization thresholds to future observations.

A0 retains positive daily-return operational scoring and the existing fallback
allocator for a comparator. A1 averages six-month and 12-1 momentum. A2 uses
0.35 each on those two factors plus 0.15 each on trend distance and SMA60 slope.
A3 multiplies by min(1,0.15/max(vol60,0.05)); A4 also applies the SPY regime
multiplier. Missing weights are retained as missing penalties, never
renormalized. Nonpositive/missing medium momentum, invalid history or unknown/
subthreshold liquidity excludes a V2 candidate. Scores are strengths, not
expected returns; predictive confidence is null and the advisory domain bridge
has confidence zero. LLM prose cannot set the score, weight, quantity or price.

SPY trend uses a 2% SMA200 distance band and the SMA60 slope sign. High
volatility is current annualized vol20 >=25% or trailing percentile >=80%.
Trailing drawdown <=-15% or downtrend reduces the multiplier to 0.25; high
volatility reduces it to 0.5. Conditions combine by minimum; insufficient data
gives zero exposure. Trend and volatility are separate dimensions. All values
are in versioned QuantPolicy, not learned from the final test.

## Portfolio, timing and friction

Capped score, inverse-volatility and risk-adjusted water filling produce existing
TargetPortfolio objects. The diagnostic risk policy has 25% position cap, 50%
sector cap, 10% minimum cash, five positions, 20% daily gross security turnover,
and 5% NAV maximum single order. Real review uses the existing supplied policy
and safety modules. Unknown equity sectors block review. No leverage or shorts.
A3/A4 enforce a conservative volatility upper bound sum(weight*volatility),
assuming correlation +1; there is no fragile high-dimensional optimizer.
Optional 60-session correlation exclusion requires sufficient aligned inputs
and is disabled by default. Market price drift is recorded separately from
permission to add risk.

Default rebalance uses 1% no-trade band, 2% maximum weight-distance trigger,
$100 minimum notional, 20% gross turnover ceiling and 1% ADV participation.
Required risk exits are not suppressed by a no-trade threshold. An infeasible
turnover/risk combination blocks the proposed trade. Expected-benefit versus
cost requires an externally supplied calibrated PIT expected return; quant
strength is never treated as one. Without it the friction estimate is
informational and the other deterministic thresholds still apply.

Baseline simulated costs are $1 commission per order and 5 bps adverse slippage
per side. Spread is unknown, not a fabricated zero observation; an explicit
spread estimate can add half-spread to adverse price. Sensitivities use 10,
25 and 50 bps slippage. Participation is a feasibility guard, not a fitted
nonlinear impact model. Taxes, securities lending and detailed exchange fees
are outside scope. Fully adjusted OHLCV is required; action coverage must be
declared. This does not model raw-price shares and a separate corporate-action
cash ledger. Backtests requiring that accounting remain unsupported.

Each close-formed target executes at the next eligible session open. The
simulator consumes only that opening price for execution and then marks to the
close. It uses whole shares, sells before buys, subtracts actual modeled fees,
reserves cash and rejects missing execution bars. NO_ACTION/BLOCKED cannot
produce fills. This isolated simulator never writes the canonical paper ledger.
The paper review packet reuses existing RiskEngine, reconciliation, OrderPlanner
and projected-portfolio validation; it grants no real-entry authority.

## Walk-forward design and actual data coverage

The fixed 23-variant plan is sealed before validation/test replay. No parameter
fitting or strategy selection occurs. Training intervals supply chronological
warmup; rolling features use only the decision's prior observations. Splits have
one eligible-session embargo and nonoverlapping test intervals. A content-bound
registry rejects a changed financial experiment over the same registered OOS;
it cannot prevent someone using another registry or dataset outside this tool.
Independent process governance remains necessary.

| Fold | Training/warmup | Validation | Untuned test |
|---|---|---|---|
| fold-1 | 2020-01-02 to 2021-01-04 | 2021-01-06 to 2021-02-11 | 2021-02-16 to 2021-04-26 |
| fold-2 | 2020-01-02 to 2021-04-26 | 2021-04-28 to 2021-05-24 | 2021-05-26 to 2021-08-19 |

Actual engineering input: six explicitly synthetic series (AAPL, MSFT, NVDA,
QQQ, GLD, SPY), 420 bars each, 2020-01-02 through the fixture end. Five symbols
are the predeclared candidate universe; SPY is the benchmark. These labels are
test identities, not actual market observations. Synthetic shocks exercise
regime and risk reduction. The two test folds contain 49 and 59 sessions;
these counts are diagnostic rows, not independent financial samples.

The real provider audit retrieved Yahoo public history for AAPL/MSFT/SPY:
825 bars each, 2023-06-26 to 2026-10-07, retrieved 2026-10-08. All were raw,
uncertified and lacked historically known-at-close observations (zero rows).
The feature gate rejected UNVERIFIED_ADJUSTMENT_BASIS and
UNVERIFIED_PRICE_SERIES. Verified action and membership histories are absent.
See [the raw audit](public-history-audit.json). No timestamps or adjustment
certifications were invented to force a financial backtest to run.

## Complete diagnostic comparisons

**The following net returns are synthetic engineering output, not investment
performance or evidence that V2 beats V1.** Candidate portfolio controls use the
same input universe, sessions, execution delay, frozen risk and base costs. SPY
buy-and-hold is a separately costed, fully invested one-time reference purchase,
exempt from candidate position/cash/turnover constraints and explicitly labeled
UNCONSTRAINED_BENCHMARK_NOT_A_POLICY_ELIGIBLE_PORTFOLIO. The tracking benchmark
is frictionless SPY. Different allocation/rebalance rules
are intentional treatment differences; signal-only conclusions require further
controlled studies. Test folds restart at $100,000; costs/turnover below sum
both folds and returns remain separate. We do not select a winner.

| Predeclared variant | Fold 1 net return | Fold 2 net return | Total costs, USD | Gross turnover |
|---|---:|---:|---:|---:|
| CASH | 0.000% | 0.000% | 0.00 | 0.000 |
| SPY_BUY_HOLD | -13.462% | 7.141% | 101.94 | 1.999 |
| EQUAL_WEIGHT | -13.907% | 2.152% | 348.84 | 2.017 |
| A0 | 9.617% | 3.934% | 1071.37 | 13.266 |
| A1 | -9.616% | 0.000% | 186.47 | 2.445 |
| A2 | -14.705% | 0.000% | 184.85 | 2.465 |
| A3 | -14.710% | 0.000% | 186.87 | 2.486 |
| A4 | -8.046% | 0.000% | 187.99 | 2.481 |
| A4_NO_MOMENTUM | -10.406% | -0.433% | 665.08 | 6.050 |
| A4_NO_TREND | -7.841% | 0.000% | 185.33 | 2.424 |
| A4_NO_VOL_ADJUSTMENT | -8.039% | 0.000% | 189.53 | 2.513 |
| A4_NO_REGIME | -14.710% | 0.000% | 186.87 | 2.486 |
| A4_NO_COST_GATE | -8.084% | 0.000% | 191.69 | 2.496 |
| A4_CORRELATION_090 | -8.242% | 0.000% | 158.93 | 2.122 |
| A4_WEEKLY | -5.337% | 0.000% | 94.53 | 1.242 |
| A4_DAILY | -8.046% | 0.000% | 187.99 | 2.481 |
| A4_MOM_WEIGHT_065 | -8.085% | 0.000% | 187.79 | 2.478 |
| A4_MOM_WEIGHT_075 | -8.013% | 0.000% | 187.71 | 2.475 |
| A4_REGIME_PERCENTILE_075 | -7.268% | 0.000% | 181.02 | 2.350 |
| A4_REGIME_PERCENTILE_085 | -8.046% | 0.000% | 187.99 | 2.481 |
| A4_COST_10 | -8.177% | 0.000% | 308.96 | 2.482 |
| A4_COST_25 | -8.515% | 0.000% | 669.68 | 2.477 |
| A4_COST_50 | -9.079% | 0.000% | 1269.41 | 2.478 |

All 92 validation/test replays completed (23 variants * 2 folds * 2 partitions).
Identical outcomes share content-addressed files: 88 distinct replay JSONs
represent all 92 evaluation rows; the archive contains 94 JSON files in total.
The correlation variant adds control to the default-disabled configuration;
it is not an ablation of an active default. No-momentum/no-trend variants retain
original weights instead of silently rescaling remaining factors. Thus both
signal content and resulting exposure can change; an equal-exposure ablation
would be a different predeclared experiment.

The full registry includes every variant, every fold, validation and test,
daily NAV/cash/exposure/turnover/cost/regime/risk-drift/decision, every simulated
trade and all metrics. CAGR/volatility/Sharpe/Sortino/drawdown/Calmar, excess
return/tracking error/information ratio, cash/exposure, hit rate, one-session
score rank IC, tails and regime counts are implemented. IC is for the aggregate
score, not a claim that each individual factor independently predicts returns.
Cash earns zero; risk-free input is zero because no treasury series is supplied.

## Uncertainty, robustness and overfit assessment

Paired moving-block intervals versus SPY use 5/20/60-session blocks, 500 draws
and seed 1729 for annualized mean daily differences. Fewer than two blocks
returns INSUFFICIENT_DEPENDENT_BLOCKS; the 60-session intervals are therefore
unavailable for these short diagnostic folds. Intervals are descriptive,
pointwise and not familywise corrected across 23 trials. Serial/cross-sectional
dependence, overlapping factor lookbacks and regime subsets reduce information.
No significance, deflated Sharpe or probability-of-overfit claim is made.
Multiple trials can create apparent winners even without true edge
([primary research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)).

Predeclared momentum-weight/regime-threshold perturbations, cost stress,
daily/weekly/threshold rebalance, factor removals and optional correlation
control are recorded for both folds. Tests also reject conflicting series,
future information, unavailable membership/sector data, missing bars and
infeasible risk/turnover; a synthetic universe perturbation verifies deterministic
behavior. Actual provider-discrepancy, real shock-period, historical-window and
survivorship robustness cannot be demonstrated with the available certified
data. **OVERFIT_RISK_UNASSESSED_FINANCIAL_DATA_UNAVAILABLE** is the correct
assessment. No OOS return advantage, regime advantage or net-cost alpha has
been established. Synthetic rankings cannot justify choosing A4 over A1/A2.

## Integration and readiness

Shipped mode is QUANT_V1_BASELINE. QUANT_V2_SHADOW is explicit opt-in, reuses
the same retrieved histories, records immutable V1/V2 scores, target differences,
quality, costs and risk, and leaves canonical orders/ledger decisions to V1.
Invalid shadow policy or history is isolated. Public bars presently produce a
blocked V2 shadow rather than an invented score. No new broker interface exists.

QUANT_V2_PAPER_CANDIDATE requires explicit policy approval/reference and a
separate review call. Daily canonical code never switches to it. The review
gate requires verified nonsynthetic OOS of at least 252 distinct sessions and
two nonoverlapping folds, exact policy/cost/risk/engine identity, fresh sanitized
Schwab-Paper account/market input, trusted metadata and all existing safety
gates. The current evidence fails that gate. The engineering happy route is
tested with declared fixtures; those tests are not financial evidence.

Rollback: set mode QUANT_V1_BASELINE (the shipped default); retain immutable
shadow/experiment records. No database migration, reset, account replacement
or canonical strategy promotion is required. Canonical doctor/paper runs were
not executed; all paper acceptance used disposable fixture runtimes. No live
broker side effect occurred.

## Reproduction and preserved records

Use Python 3.12 and the frozen development dependencies from DEVELOPMENT.md:

```powershell
.\.venv\Scripts\python.exe scripts/validate_repo.py
.\.venv\Scripts\python.exe scripts/quant_diagnostic.py --output .tmp/quant-v2/new-diagnostic
.\.venv\Scripts\python.exe -m meridian quant inspect --dataset DATASET.json
.\.venv\Scripts\python.exe -m meridian quant backtest --dataset DATASET.json --plan PLAN.json --output .tmp/quant-v2/financial-oos
```

For the packaged synthetic dataset pass the explicit --diagnostic flag to
quant backtest. Unzip [the full registry](experiments/synthetic-full-registry.zip)
to an isolated directory and replay its synthetic-dataset.json with plan.json.
The sealed plan contains declared_at, so generating a new plan changes its
hash; replaying the saved plan/dataset under the same engine reproduces the
content hashes. [Archive manifest](experiments/archive-manifest.json) verifies
each JSON and the ZIP. No personal account, credential or canonical database
is in the archive. No stale local path is needed for reproduction.

Engine hash: 71f5293d1a595e3cad212f732a244ab9351fcf1892c5d17e52ecd9658c9c4f87
Dataset hash: 06605fe1644d2affb631040f290b690295627ea6451370483b2679e83a4f8f3c
Plan hash: 0bdbd11dbc7d67902f6399217505d381509c21c9602057bb007ed59d4e5ca23b

## Required seven conclusions

1. V2 is implemented in domain-connected modules, CLI, shadow and separate paper
   review; it is not merely a collection of experiment files.
2. Multi-horizon PIT signals, bounded ranks, explicit missing data, volatility/
   regime risk ceilings, costs/no-trade decisions and delayed reproducible replay
   materially replace one-day scoring as a challenger, preserving V1 by default.
3. Better strict financial OOS performance: **not demonstrated**.
4. Positive net-cost alpha: **not demonstrated**; cost accounting/stress tests pass.
5. Anti-lookahead invariants are tested; real-data integrity/survivorship and
   overfitting remain unverified. Public data is rejected for financial evidence.
6. Safe V1-compatible shadow/review integration exists. Canonical promotion and
   operational candidate readiness remain blocked pending evidence and review.
7. Real broker side effects: **none**. Canonical runtime and ledger were untouched.
