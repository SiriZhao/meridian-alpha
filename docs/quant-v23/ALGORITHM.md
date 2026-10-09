# Quant V2.3: bounded shadow portfolio challenger

Status: implemented research engine, not a validated return forecast. Base:
`origin/codex/research-terminal` at `3c02dd2`. V1, V2.1 and V2.2 source,
policies and archived experiments remain unchanged. Production remains V1.

## File/function audit and resulting choices

| Existing component | Mathematical meaning / finding | V2.3 treatment |
|---|---|---|
| `daily_closure.DailyClosureService._run` | Positive same-day return with confidence=1; operational scoring, not calibrated predictive probability | Preserve as A0 reference; no production edits |
| `alpha_fusion`, `candidates.CandidateSelector` | Evidence/research prioritization, not independent expected-return estimation | Do not use prose or candidate confidence as portfolio forecast |
| `allocation.DeterministicFallbackAllocator.allocate` | Capped proportional positive-score preference, excess budget stays cash | Preserve V1 comparison; no risk relaxation |
| `quant.features.compute_features` | Completed contiguous 21/63/126/252-session momentum, 252-to-21 skip, adjusted OHLCV and cutoff gates | Reuse; these are session proxies, not calendar-month French momentum |
| `quant.features.compute_challenger_features` | Medium distance, acceleration, trend sign instability, retrospective residual momentum | Keep acceleration/residual/reversal diagnostic; no evidence justifies new score weights |
| `quant.signals.score_challenger` | Six fixed factor weights, signed saturation and bounded tied-rank blend | Preserve; near ties can still change ranks and saturation loses tail magnitude; no fitted rank transforms |
| `quant.regime.detect_regime` | SPY trend and volatility dimensions, policy-defined exposure ceiling | Preserve; state is a risk conditioning observation, not a confident market forecast |
| `quant.portfolio.allocate_challenger` | One inverse-vol step, correlation-cluster caps, conservative volatility bound, shrunk covariance diagnostic | Reuse baseline; make valid shrinkage actionable in bounded allocation objective |
| `risk.RiskEngine.approve` | Hard position/sector/cash constraints; missing metadata blocks | Reuse in replay; no inferred sectors/ETF constituent exposures |
| `orders.OrderPlanner.plan`, `ProjectedPortfolioValidator` | Separate quote entitlement, whole shares, cash; proposed sells are not buy proceeds | Unchanged; V2.3 has no execution route or quote certification |
| `quant.portfolio.challenger_rebalance` | Bands, threshold, participation, turnover, explicit commission/slippage; spread unknown | Reuse after construction, expected benefit stays null |
| `quant.backtest.WalkForwardRunner.run/_signal` | Close decision, next-session open, sells-before-buys with actual simulated cash, adjusted-coordinate units | Subclass signal hook; reuse all original fill/cash/preflight gates |
| `historical.YahooChartHistoricalProvider` | Retrieval availability is today, not historical knowledge; RAW shadow contract | Preserve live adapter; separate retrospective receipt captures adjustment/events without PIT fabrication |
| `live_quant_bridge.build_live_quant_snapshot` | Qualified V2.2 or restricted public within-session diagnostics | Unchanged; opt-in V2.3 packet is separate SHADOW_ONLY evidence, not automatic promotion |
| `research_backtest.ResearchBacktestRunner` | Independent directional research cells, not self-financing portfolio returns | Do not reinterpret as portfolio backtest |
| `alpha_lab`, `portfolio_lab.evaluate_portfolios` | Reviewed forward pairs / predeclared horizon round trips with dependent observations | Preserve archives; no double-counting as continuous buy-and-hold evidence |
| `shadow_evaluation` | Research grounding/repeatability/promotion evidence | Engineering quality does not establish trading alpha |

The six signal factors remain: 3m absolute (.10), 6m absolute (.15), 12-1
(.25), relative 6m (.25), medium trend distance (.125), persistence (.125).
Lookbacks require completed sessions and historical availability at cutoff.
Volatility, drawdown, liquidity, beta and correlation are risk inputs, not
additional calibrated alpha. Missing inputs retain their explicit unknown /
rejection semantics. Release-dated fundamentals remain disabled.

## New construction, and its economic hypothesis

Let `a` be V2.2's feasible inverse-vol target, `c` current weights, and
`S = .5 diag(sample covariance) + .5 sample covariance`. Default objective:

`J(w) = sum((w-a)^2) + .10 * w'Sw/.15^2 + .02 * sum(abs(w-c)) + assumed_cost(w,c)/NAV`.

The last term uses actual configured commission per changed holding and
adverse slippage/spread assumption. It is a weight-level estimate; final
whole-share feasibility and no-trade bands remain in the existing replay.
Unknown spread stays unknown even when the numerical cost assumption omits it.
`J` compares ordinal preference, variance and friction; its units are NOT
expected profit. No economic benefit gate is fabricated from a score.

Hypothesis: covariance-aware diversification and persistence of holdings can
reduce unnecessary risk and friction. Failure modes: covariance instability,
conservative underinvestment, lag after shocks, local-grid quantization, and
misleading apparent Sharpe improvements caused solely by lower exposure.
Risk weight .10 and turnover .02 were fixed before evaluation, not fitted.

`SHRUNK_RISK_BUDGET` replaces variance/turnover objective with normalized risk
contribution error against V2.2 anchor budgets plus target/exposure distance.
It is not equal risk contribution and has no global optimum guarantee.
`REGIME_CONDITIONED` additionally caps absolute beta budget .60, downside
budget .10 and trend instability .50. Missing required inputs propose cash
with an explicit refusal reason; this is not authorization to sell holdings.
Budgets apply to the feasible target, not a guarantee about actual partial fills.

Every proposal satisfies original position/count/sector/cash limits, positive
correlation component cap .40 and worst-positive-correlation vol bound .15.
The constructor refuses leverage, shorts, non-finite correlations and weakened
V2.2 ceilings. At most four descending grid steps, eight sweeps, eight securities;
default .02/.01/.005 and two sweeps. Coordinate moves use cash and deterministic
lexical tie handling. Missing/invalid covariance keeps conservative V2.2 fallback.

## Identity, integration and rollback

`flagship_policy`, `flagship_portfolio`, `flagship_replay`, `flagship_packet`
compose existing FeatureSnapshot, ChallengerScore, TargetPortfolio, RiskEngine
and cost-aware rebalancing. The packet exposes actual factors, scores, prior
score attribution, preferred/feasible/cost-adjusted target, hashes and unknowns.
It never creates orders. Public receipts cannot enter this qualified interface.

Numerical engine identity hashes frozen dependency engine plus policy,
constructor and replay source. Experiment/data/packet hashes are separate.
V2.2 engine remains `e510e84d05b227e2ed2333ff886d4906ecd7a80ac4e5b925c964e91567df821c`.
Rollback: stop invoking the opt-in V2.3 API/scripts; existing V1 and V2.2 paths
are unchanged. No account migration, ledger reset, model authority or paper
switch was introduced.

Economic references: [French prior 2–12 month momentum](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html),
[Hautsch/Voigt on allocation with transaction-cost regularization](https://arxiv.org/abs/1709.06296).
They motivate hypotheses; they do not validate Meridian performance.
