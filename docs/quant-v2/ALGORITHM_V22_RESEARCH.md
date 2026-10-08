# Quant V2.2 algorithm-first research — 2026-10-08

Financial status: ALPHA_NOT_YET_DEMONSTRATED. Real financial validation pending.
Engineering acceptance and diagnostic totals are recorded below only after
execution. This challenger is SHADOW_ONLY; the production policy remains V2.1
QUANT_V1_BASELINE. No calibrated expected-return model was fitted.

## Economic hypotheses and measurements

| Included input | Window / measurement | Group weight contribution | Hypothesis and failure mode |
|---|---|---:|---|
| momentum_3m | P[t]/P[t-63]-1 | .10 | Medium price continuation; abrupt rebounds/reversals can invalidate it. |
| momentum_6m | P[t]/P[t-126]-1 | .15 | Persistent intermediate strength; sensitive to endpoint shocks. |
| momentum_12_1 | P[t-21]/P[t-252]-1 | .25 | Longer continuation excluding the recent month; lag and overlapping signals. |
| relative_momentum_6m | 126-session stock return minus aligned SPY return | .25 | Separates market appreciation from relative strength; subtraction is not market-neutral alpha. |
| medium_distance | P[t]/SMA60[t]-1 | .125 | Intermediate trend confirmation; large positive distances may be overextension. |
| trend_persistence | fraction of positive daily returns in 60 sessions minus .5 | .125 | Breadth of a symbol's trend over time; ignores daily return magnitude. |

All inputs use completed, contiguous, matching, fully adjusted PIT rows known by
cutoff. The 21/63/126/252-session proxies are not the precise monthly CRSP
construction in the [French momentum definition](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html).
The economic hypotheses are unproven for this universe, not forecasts.

Diagnostics excluded from the trading score: acceleration is the difference
between consecutive 63-session returns; instability is the fraction of 20 sign
changes around rolling SMA60; residual momentum is sum(r_stock-beta60*r_SPY)
over 63 sessions, using same-cutoff trailing beta. It assumes stable beta and
is not a fitted expected return. Existing SMA200, volatility20/60, downside RMS,
ATR14, trailing drawdowns, beta/correlation, ADV and short reversal remain
inspectable. Fundamentals and broad-market participation are unknown.

## Fusion and attribution

Absolute/relative/trend group weights are .50/.25/.25. For raw signed x and
fixed scale s, a=(1+x/(abs(x)+s))/2. Scales are .10 for momentum/relative, .05
for distance, .20 for centered persistence. Tied rank r=(below+ties/2)/N and
b=.20*(N-1)/(N+4); u=(1-b)*a+b*r. The fixed absolute anchor retains magnitude
and avoids the N=4/5 normalization switch. Tiny tie breaks still change ranks;
the blend bounds their influence rather than claiming perfect continuity.

Signal strength=sum(weight*u); missing factors contribute zero with their
original mass and explicit reasons, without hidden reweighting. Positive
six-month absolute momentum, qualified liquidity, verified history and known
regime are eligibility gates. Predictive confidence is null, never probability
of profit. Ordinal rank ties use lexical identity for reproducible processing.

Reported risk-adjusted score=eligible strength*min(1,.15/max(vol60,.05))*regime
multiplier. Allocation uses eligible strength, not that adjusted score: one
inverse-volatility sizing step, caps, and one exposure/volatility ceiling. Score
changes attribute raw factor contributions and eligibility separately; risk-score
changes separate signal/eligibility effects from changes in risk transformation.
Persistence counts observed eligible sessions, never predictive confidence.

## Portfolio and costs

Preferred weights are unconstrained proportional strengths within the cash
budget. Feasible targets apply position/count caps, SPY exposure ceiling,
correlation-component caps (.80 positive correlation, .40 aggregate weight),
PIT sectors, and the conservative +1-correlation volatility bound. Components
use single-link connections; this may conservatively group indirect peers.
Unknown/invalid correlation reduces exposure to at most .25. No sector or ETF
lookthrough is guessed. Unknown sectors cannot create feasible equity targets.

A separate estimate uses .50 fixed diagonal covariance shrinkage with a PSD
check. This is a declared robustness diagnostic, not estimated optimal shrinkage
or a replication of [Ledoit/Wolf](https://ledoit.net/honey.pdf). The hard risk cap
uses sum(weight*max(vol60,.05)), not that estimate. Ex-ante ceilings can miss
future realized volatility during shocks; no tracking-accuracy claim is made.

Cost-adjusted targets reuse existing bands, $100 minimum trade, 20% gross
turnover, 1% ADV participation and hard order/cash constraints. Costs are $1
per order and 5bps adverse slippage per side, with 10/25/50bps stress. Unknown
spread stays unknown; no impact coefficient is invented. No-action has zero
turnover and charged costs. Expected-return benefit remains unknown unless an
independently reviewed contract binds mature training labels, horizon, model/
data/feature identities and the final post-band/turnover proposal. A review flag
is an external attestation, not cryptographic proof of calibration.

Research packets distinguish preferred, feasible, cost-adjusted and eligible
hypothetical changes. Account absence leaves current exposure/currency costs
unknown. Existing gates/planner/projected validation and an all-buy/no-sell-fill
scenario guard additions. A recommendation is not a fill or authorized order.

## Predeclared evaluation

New frozen plan: 19 variants, the two original chronological folds, validation
and test. Comparators: CASH, unconstrained SPY reference, capped SPY_POLICY,
equal weight, A0-A4, V22, matched-budget V22, neutral absolute/relative/trend
groups, rank blend .15/.25, and 10/25/50bps cost stress. All share dataset,
hard risk limits, modeled fees, information cutoffs and next-session-open fill
engine except the explicitly unconstrained SPY reference. A0-A4 here use common
declared allocation/rebalance controls; their archived V2.1 experiment is never
overwritten or silently equated with this new treatment.

Neutral ablations replace available group contributions with .5 without
reweighting other groups; missing observations remain missing. They retain
eligibility gates and declare .25 nominal exposure with the matched control.
Risk ceilings, rounding, no-trade bands and partial simulated fills may reduce
or change realized exposure. A paired exposure audit therefore qualifies each
comparison; unequal actual exposures do not isolate predictive alpha.

Only SYNTHETIC_DIAGNOSTIC inputs are available (six labeled fixture series,
420 bars, five candidate identities). Original 49/59-session test folds are
short, dependent engineering samples. Existing metrics and moving-block
intervals are descriptive, not multiple-testing-adjusted significance. There
is no final financial OOS tuning, winner selection or genuine alpha claim.
Real adjustment vintages, actions, dated membership/metadata, exceptional
calendar closures, delistings and survivorship still need independent proof.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts/quant_v22_diagnostic.py --output .tmp/quant-v22/new-run
.\.venv\Scripts\python.exe -m meridian quant backtest --dataset DATASET.json --plan PLAN.json --output .tmp/quant-v22/replay --diagnostic
.\.venv\Scripts\python.exe -m meridian quant packet --dataset DATASET.json --cutoff 2021-02-11T21:00:00+00:00 --diagnostic
.\.venv\Scripts\python.exe scripts/validate_repo.py
```

Use the saved new plan to reproduce its declared timestamp/identity. Original
V2.1 exact hashes require pinned 4664cb4 and its saved plan, not the new engine.
Financial input must omit --diagnostic and independently satisfy all data gates.

## Executed results and acceptance

Pending completion of the frozen diagnostic and final repository validation.
