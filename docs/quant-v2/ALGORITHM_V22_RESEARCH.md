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

All 76 evaluations completed under the predeclared 19-variant plan: two folds,
validation and test, 76 distinct deterministic replays. The following table
reports every test variant, including cost stresses and uninformative no-trade
outcomes. Returns are cumulative **synthetic** net returns, never financial OOS
evidence. Exposure is the average realized invested fraction; costs are modeled
USD for the $100,000 starting account. The full registry retains all validation
results, risk/regime diagnostics, metrics and uncertainty intervals.

| Variant | Fold 1 net % | Cost USD | Exposure % | Fold 2 net % | Cost USD | Exposure % |
|---|---:|---:|---:|---:|---:|---:|
| CASH | 0.000 | 0.00 | 0.00 | 0.000 | 0.00 | 0.00 |
| SPY_BUY_HOLD | -13.462 | 50.97 | 99.99 | 7.141 | 50.97 | 99.98 |
| SPY_POLICY | -3.068 | 39.69 | 23.44 | 1.475 | 20.49 | 23.88 |
| EQUAL_WEIGHT | -13.392 | 90.27 | 81.76 | 2.261 | 73.91 | 83.36 |
| A0 | 9.613 | 319.54 | 36.01 | 3.934 | 750.68 | 48.58 |
| A1 | -9.608 | 179.05 | 19.89 | 0.000 | 0.00 | 0.00 |
| A2 | -14.710 | 186.87 | 26.93 | 0.000 | 0.00 | 0.00 |
| A3 | -14.710 | 186.87 | 26.93 | 0.000 | 0.00 | 0.00 |
| A4 | -8.046 | 187.99 | 17.36 | 0.000 | 0.00 | 0.00 |
| V22 | -7.783 | 194.87 | 17.66 | 0.000 | 0.00 | 0.00 |
| V22_NEUTRAL_ABSOLUTE | -2.778 | 73.89 | 6.57 | 0.000 | 0.00 | 0.00 |
| V22_NEUTRAL_RELATIVE | -2.809 | 69.55 | 6.69 | 0.000 | 0.00 | 0.00 |
| V22_NEUTRAL_TREND | -2.795 | 72.71 | 6.59 | 0.000 | 0.00 | 0.00 |
| V22_MATCHED_BUDGET | -2.753 | 77.96 | 6.49 | 0.000 | 0.00 | 0.00 |
| V22_RANK_BLEND_.15 | -7.788 | 199.84 | 17.68 | 0.000 | 0.00 | 0.00 |
| V22_RANK_BLEND_.25 | -7.782 | 194.55 | 17.63 | 0.000 | 0.00 | 0.00 |
| V22_COST_10 | -7.908 | 319.74 | 17.67 | 0.000 | 0.00 | 0.00 |
| V22_COST_25 | -8.262 | 693.98 | 17.67 | 0.000 | 0.00 | 0.00 |
| V22_COST_50 | -8.763 | 1294.03 | 17.49 | 0.000 | 0.00 | 0.00 |

V22's fold-1 loss is slightly smaller than A4's while cost and average exposure
are higher; this small synthetic difference is not evidence of predictive
improvement. A0 is positive on these fixtures, and adding factors does not make
the challenger a winner. Increasing slippage worsens V22's fold-1 result. The
second fold's zero outcomes reflect eligibility/risk/no-trade decisions and
contain no active-trading evidence for A1-A4 or V22.

The 12 paired exposure audits include six within .001 tolerance, all in fold-2
validation/test where both arms have zero exposure: these are uninformative.
The other six are not matched; maximum per-session exposure difference is
.019138377170545073 (1.91 percentage points). Nominal matched-budget tests pass,
but **no isolated factor alpha conclusion** follows from the realized ablations.
Group-neutral replacements retain the eligibility gates; they do not remove the
absolute-momentum gate or disentangle every shared feature dependency.

Statistical uncertainty uses paired moving blocks (5/20/60 sessions, 500
repetitions, fixed seed 1729). Sixty-session intervals are unavailable on these
short test folds; shorter-block intervals are pointwise descriptive summaries,
not familywise correction, causal evidence or independent financial samples.
No strategy was selected from these results. Parameter and cost sensitivity
here are engineering diagnostics; real universe/provider/shock robustness and
survivorship bias remain unresolved. Certification strings, policy approval
references and registry timestamps are attestations requiring external review.

Frozen identities:

- Engine source: `043499eda8dbbebb833968d97e72c376bba553e93e820013fc013124ca9837bb`
- Challenger policy: `e0e0c2a4972a1cce7e18a64480ca2b6798a0002a04772ff58235a74592077674`
- Dataset: `06605fe1644d2affb631040f290b690295627ea6451370483b2679e83a4f8f3c`
- Plan: `642288f0e8ffb8e1b542d17750e8ec79042f31c562432359e9672a35f3790474`

The new immutable archive contains 82 JSON records. Seven additive V2.2 schemas
and the archive are verified by `scripts/validate_quant_v22_artifacts.py`.
The old five schemas and V2.1 archive were preserved byte-for-byte. An independent
GitHub clone pinned at `4664cb4` reran the original 92 evaluations / 88 distinct
replays; its summary and every replay JSON matched the original archived
payload exactly. See `experiments-v22/v21-reproduction-proof.json`.

### Acceptance and authority

Implementation commit: `c5dc594`. Targeted acceptance: 165 passed in 103.65s;
Ruff passed and Pyright reported zero errors/warnings. Restricted Windows full
validation produced 954 passed / one failure in the existing native child-tree
timeout test (cleanup could not terminate descendants within ten seconds).
Approved-host full validation subsequently passed: **955 passed in 192.81s**,
dependency integrity, Ruff, Pyright, both artifact registries, CLI smoke and
optimized isolated safe-paper acceptance all passed. The native timeout test
passed in this environment; no safety test was removed or weakened.
Independent-clone/Windows/Linux CI results will be recorded after execution.

Runtime and authority remain V1 baseline, broker submission disabled, no paper
promotion, no canonical database writes or migrations, and no live orders. The
V22 policy can only be SHADOW_ONLY; research packets cannot authorize trades.
Rollback is to continue the existing V1 default and omit the optional challenger
or packet route. Original V2.1 paper-review and shadow controls remain unchanged.
Financial validation and calibrated expected return are pending; paper-candidate
readiness is INSUFFICIENT_EVIDENCE. Alpha remains ALPHA_NOT_YET_DEMONSTRATED.
