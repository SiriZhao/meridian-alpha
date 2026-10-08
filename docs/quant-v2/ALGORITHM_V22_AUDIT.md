# Algorithm audit v2.2 — 2026-10-08

## Recovered state and baseline

Initial mission verified origin SiriZhao/meridian-alpha, Quant worktree at 4664cb4, clean local
and remote codex/quant-engine-v2; parent fd7481d is already integrated into the Quant branch. PR 3 is open,
draft, mergeable, with no comments/reviews. Original checkout is the separate
Forward Evidence branch and clean. No reset, overwrite or main development.
Python 3.12 project environment; targeted baseline: 135 passed in 91.07 seconds
(106 Quant, 21 manual-authority, eight replay-integrity tests).

## File/function gap inventory

| Location | Mathematical/implementation finding | Bounded correction |
|---|---|---|
| features._compute | h-session endpoints P[t]/P[t-h]; 12-1 P[t-21]/P[t-252] are correct. SMA slope windows end t and t-20. Fully adjusted OHLCV and aligned SPY are required. | Keep these definitions; add explicit medium distance, acceleration, instability and residual diagnostics using the same eligible rows. |
| features.eligible_bars | Sorts rows; source disorder is hidden by sorting, although duplicate identities are rejected by the historical domain. | Challenger rejects out-of-sequence source sessions; future valid appended rows cannot change a prior feature snapshot. |
| signals._normalize | At N=4 versus N=5 or all ties, transform switches from absolute bounded strength to pure rank. Tiny differences between otherwise tied peers can span [0,1]. | Fixed-scale bounded strength blended with a small, smooth N-dependent tied-rank term; declare the remaining discontinuity and bound its weight. |
| QuantFactorEngine.score | Two momentum/two highly related trend measures; computed relative momentum is unused. Missing weights are retained, which is correct. A0 clips extreme >100% one-day returns. | Challenger separates absolute, market-relative and trend groups; diagnostics do not all enter the score. Preserve original variants unchanged. |
| QuantFactorEngine.score / allocate | A4 score multiplies volatility and regime; risk-adjusted allocation divides by volatility again, then portfolio volatility caps and regime exposure apply. The common regime factor cancels during normalized allocation except eligibility, yet obscures attribution. | Report predictive strength, risk transformation and allocation separately. Use one inverse-vol sizing step and one portfolio risk/exposure cap. No claim that de-risking increases alpha. |
| portfolio.allocate | Greedy correlation exclusion drops peers completely. Default correlation control is absent. +1 volatility bound is safe but not a covariance-based estimate or measured target tracking. | Proportional connected-component concentration caps, explicit unknown-correlation budget, a separate fixed-shrinkage estimate with a PSD check, and the existing conservative bound as the hard ceiling. |
| portfolio.cost_aware_target | Correct no-action zero-cost accounting; commissions/slippage assumptions explicit. Optional bare expected_improvement has no horizon, training or provenance contract. | New typed externally reviewed estimator interface; no calibrated estimate => EXPECTED_RETURN_UNCALIBRATED. Keep unknown spread explicit and do not infer market impact. |
| backtest.WalkForwardRunner | Close signal/next-open execution, membership and actions gates, whole shares, sell-before-buy actual simulated cash are correct. Partial fills mean desired exposure differs from actual. | Extend this runner with an optional challenger; same fill engine, metadata and hard controls. Report target versus realized exposure in research. |
| experiments.run_experiments | Plans sealed before replay, no fitting. Original ablations change exposure as well as signal. Registration is an attestation, not authenticated global prevention of OOS reuse. | Separate v2.2 manifest; explicit neutral-group, fixed-budget ablations; never describe unequal realized exposure as an isolated alpha effect. |
| integration.plan_paper_candidate | Existing gates and post-planner sector checks protect incomplete sells. Real OOS lacking => insufficient evidence. | Research packet uses the same planner and projected validator for hypothetical eligible changes, never paper promotion or ledger writes. |
| live_advisory | Public quote freshness is not execution entitlement; qualitative confidence is not quant calibration. | Add a typed research packet boundary only; do not replace live advisory, account truth or authority gates. |
| regime.detect_regime / features._compute | The 252-price maximum drawdown is a trailing stress memory, not current drawdown from the latest peak. Stress can persist after price recovery. A 252-price window contains 251 returns; 252-session momentum needs 253 prices. | Retain the conservative risk rule and explicit window semantics. Do not describe it as a confident market forecast or relax it after inspecting synthetic returns. |

## Research qualifications

Relative return is not market-neutral alpha; beta-adjusted residual sums assume
a stable trailing beta and are diagnostics, not a calibrated forecast. Trend
and momentum overlap, tied ranks retain some discontinuity, correlation clusters
can connect through a chain, and volatility estimates lag shocks. Thresholds
are predeclared risk rules rather than market probabilities.

Public bars still lack authenticated adjustment vintages, actions, historical
membership/sector/calendar proof. Fully adjusted share replay does not provide
a raw-share dividend/split cash ledger. Delistings cannot be invented. No real
financial OOS, actual shock robustness, overfitting assessment or survivorship
resolution follows from synthetic fixtures. Original V2.1 files remain immutable;
exact archived replay requires its pinned engine commit, never relabeling it as
V2.2. Challenger predictive_confidence remains null.

## Resumed audit at 5bdb7a4

The implementation, registry and wheel correction were already committed and
pushed when this session resumed. The remaining audit/research/acceptance and
two reproduction proofs were preserved. Current targeted baseline: 165 passed
in 109.57 seconds. Original checkout and remote foundation remain fd7481d;
Quant PR 3 is draft and mergeable. Both exact-code CI runs succeeded.

Two further gaps require deterministic guards before final handoff:

- `packet.build_research_packet`: the all-buys/no-sells scenario rechecks cash,
  sectors, overall exposure and volatility, but omits correlated-component and
  unknown-covariance exposure budgets. A safe intended rotation can therefore
  depend on a sell filling to satisfy its challenger concentration policy.
- `portfolio.allocate_challenger`: a sector-map key with value None is accepted
  without identifying whether it is an ETF exemption or unknown equity sector.
  Normal typed metadata rejects an equity with no sector; the packet now also
  rejects invalid caller objects that bypass that validation. Unknown classifications must
  block additions; an ETF exemption requires explicit PIT asset-type metadata.

The resumed changes preserve the original V2.1 and V2.2 archives and parameters.
New engine diagnostics will use a separate immutable directory; observed
synthetic returns will not determine a threshold or weight change.

## Resumed corrections and measured boundary

`portfolio.challenger_budget_violations` reuses the existing risk estimate to
check overall, volatility, correlated-component and unknown-covariance budgets.
`packet.build_research_packet` applies it after bands/turnover and under the
all-buy/no-sell scenario. That scenario lowers NAV by declared modeled friction;
worst-case draft notionals and the friction model are conservative research
assumptions, not observed fills. Missing volume/volatility stays unknown.
`allocate_challenger` requires explicit DIVERSIFIED_ETF metadata for a missing
sector exemption. No sector or ETF overlap is inferred.

`WalkForwardRunner.run` uses prior-close risk inputs and opening marks, deducts
modeled friction from proposed NAV, and blocks new buys outside these budgets.
Blocked buys create no fill/fee/turnover. Price-driven risk drift is recorded
separately; the controls cannot guarantee future market exposure or volatility.
`score_challenger` starts persistence at one when previously blocked inputs
become eligible within the same completed session; it remains uncalibrated.

Five pre-fix concentration/classification cases and two friction-NAV stress
cases reproduced failures. Final challenger tests: 46 passed in 20.57 seconds.
The earlier first-hardening full run passed 968 tests; final source validation,
independent replay and CI are recorded in ACCEPTANCE_V22.md when completed.
Final engine: e510e84d05b227e2ed2333ff886d4906ecd7a80ac4e5b925c964e91567df821c.
Factor weights, thresholds, policies, frozen plan and old archives are unchanged.
