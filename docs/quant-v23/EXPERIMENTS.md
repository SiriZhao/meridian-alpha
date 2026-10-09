# Fixed experiments and honest financial scope

No selected winner or automatic strategy promotion. `plan.json` is sealed before
evaluation; its dataset and numerical engine identities must match on replay.
Existing V2.1/V2.2 frozen registries are retained byte-for-byte.

The 22 predeclared variants cover CASH, unconstrained SPY reference, policy SPY,
equal weight, A0–A4, V2.2, three V2.3 constructions, paired V2.2/V2.3 cost tiers
(zero explicit friction, 25bps, 50bps), risk-weight .08/.12, and removal of both
turnover/cost objective penalties. Inverse-vol is already V2.2 construction and
is tested for exact equality rather than advertised as a new algorithm.
All policy comparisons share universe, cutoffs, hard constraints and fills.
SPY reference is explicitly unconstrained; it is not a policy-eligible target.

Existing two chronological folds are reused: train, validation, test with one
excluded exchange session between partitions; non-overlapping final test folds.
Parameters are fixed and no fitted transformation uses validation/test returns.
One-session next-open labels need one-session embargo. Multi-horizon overlapping
labels would need a different purge/embargo plan and are NOT evaluated here.
All 88 runs are SYNTHETIC_DIAGNOSTIC, not 88 independent financial experiments.
Fold-2's weak signals may correctly yield no action. Record zero trades rather
than forcing exposure to manufacture research results.

Reproducible commands (project Python 3.12; frozen `uv.lock`):

```powershell
.venv\Scripts\python.exe scripts\quant_v23_diagnostic.py --output .tmp\v23-reproduction --freeze-only
.venv\Scripts\python.exe scripts\quant_v23_diagnostic.py --output .tmp\v23-reproduction
.venv\Scripts\python.exe scripts\quant_v23_public_research.py --cache .tmp\v23-public-cache --output .tmp\v23-public-research --download-missing
.venv\Scripts\python.exe scripts\validate_quant_v23_artifacts.py
.venv\Scripts\python.exe scripts\validate_repo.py
```

Public references use latest downloaded adjusted close on a fixed common window,
actual calendar-year CAGR, zero-risk-free Sharpe/Sortino, drawdown, Calmar, Ulcer,
beta/capture, paired 20-session moving-block uncertainty and four entry/terminal
exit cost assumptions. These are unconstrained buy-and-hold diagnostics, not
executed fills or certified OOS strategy results. No V2.3/V1 financial comparison
is fabricated where history availability and membership are unqualified.

## Attempt / failure register

* Initial prototype engine `d97ce3...` completed a synthetic registry while a
  source hardening edit was made. It is superseded and excluded from acceptance;
  a fresh frozen directory evaluates `38c61f...` alone. Old local evidence stays.
  A final non-finite-factor input guard superseded that intermediate registry;
  the accepted numerical engine is `7d85f0...`, 88 complete replays. No intermediate
  registry is used to claim acceptance, select coefficients or financial alpha.
* Packet evidence labeling initially compared the wrong synthetic enum string.
  A regression caught it; the final API derives the class from the underlying
  `synthetic` flag. No incorrect packet was promoted or delivered as real evidence.
* Source packaging initially left runtime lock directories under policies/schemas.
  Full regression found four existing configuration tests failing to read those
  directories. Preserve the tests; fix the offline generator to produce source
  artifacts without runtime locks. Local guard evidence was moved into isolated
  `.tmp` and the old tests plus a no-lock/no-overwrite regression now pass.
* The first full validation attempt stopped at public-parser typing errors;
  validated column narrowing fixed the implementation without type suppressions.
* Initial public receipt filename used response hash only: repeated retrieval
  changes availability metadata. Fixed by separate receipt-content identity;
  raw response retains its byte hash. No immutable object overwritten.
* Small-universe covariance unknown: constructor preserves capped conservative
  V2.2 fallback instead of using zero correlation or a fragile optimizer.
* Fundamental / expected-return / ETF overlap models remain disabled because
  evidence is missing, not because their synthetic scores were unfavorable.
* Extra residual/acceleration/reversal predictors were not activated: no
  independent marginal predictive evidence and correlated factor redundancy.
* Dynamic risk budgeting is only an ex-ante target control. It can lag sudden
  beta/volatility changes or incomplete simulated exits; existing risk drift
  remains reported. It is not proof of higher net alpha.

Metrics and results are retained in `synthetic-summary.json` and
`public-exploratory-summary.json`. Paired intervals are descriptive pointwise,
not multiple-trial-corrected. Exposure/cash/turnover/trades accompany returns;
lower risk alone cannot establish better alpha. Financial conclusion remains
ALPHA_NOT_YET_DEMONSTRATED regardless of which synthetic variant appears best.

## Recorded synthetic test-fold comparison (not financial evidence)

| Variant | Fold-1 cumulative return | Mean exposure | Trades | Costs (fixture USD) | Gross turnover |
|---|---:|---:|---:|---:|---:|
| A0 | 9.6130% | 36.01% | 115 | 319.54 | 4.0436 |
| A1 | -9.6077% | 19.89% | 64 | 179.05 | 2.3752 |
| A4 | -8.0458% | 17.36% | 67 | 187.99 | 2.4810 |
| V2.2 | -7.7827% | 17.66% | 70 | 194.87 | 2.5616 |
| V2.3 shrinkage budgets | -7.4300% | 17.43% | 70 | 193.11 | 2.5199 |
| V2.3 cost constrained | -7.1662% | 16.67% | 69 | 185.76 | 2.3894 |
| V2.3 regime conditioned | -7.1662% | 16.67% | 69 | 185.76 | 2.3894 |

Fold-2: A0 return 3.9342%, exposure 48.58%, 280 trades, cost 750.68;
A1/A4/V2.2/all three V2.3 targets remained cash, zero returns/trades/costs.
Regime budgets did not add value in this fixture. No component receives an
alpha endorsement. An exposure-controlled financial ablation remains blocked;
the old V2.2 matched-budget archive is retained as engineering evidence only.

Real PUBLIC_EXPLORATORY buy-and-hold references on the fixed common observed
window (2021-01-04–2025-12-31), 1254 return intervals: SPY calendar CAGR 14.69%,
QQQM 15.52%, AAPL 16.67%, MSFT 18.33%, NVDA 70.36%; respective maximum drawdowns
-24.50%, -35.04%, -33.36%, -37.15%, -66.34%. These are survivor-selected,
latest-vintage, unconstrained reference statistics with no V2.3 OOS authority.
All five and all cost tiers are retained; NVDA's exceptional past result is
not a selection rule, return forecast, or evidence against survivorship bias.
