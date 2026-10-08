# ADR 0036 — PIT Quant Engine V2, delayed evaluation and shadow isolation

Date: 2026-10-08. Status: implemented challenger architecture; promotion disabled.

## Problem

The operational closure scores positive single-day returns with constant
confidence=1. It cannot express medium-term strength, signal stability,
liquidity uncertainty or an interpretable sample-out evaluation. Existing
research backtests evaluate directional prose, not portfolio execution.

## Decision

Extend project-owned `HistoricalBarSeries` into versioned `FeatureSnapshot`
and `AlphaScoreV2` contracts under `meridian.quant`. Prices must be positive,
contiguous completed sessions, genuinely available at the decision cutoff,
verified and explicitly fully adjusted. Public histories retrieved today keep
their actual availability and remain rejected for historical PIT evaluation.
No fills or prices are inferred from LLM output, missing volume or recommendations.

Compose explicit momentum/trend groups through contemporaneous tied ranks;
small/tied populations use a fixed bounded absolute transform. Missing factors
retain their original weights and an explicit penalty. Forecast confidence is
uncalibrated (`None`), not operational confidence=1. Risk features budget risk;
fundamentals and valuation remain unavailable without release-dated PIT inputs.

SPY provides simultaneous trend and volatility dimensions. No future regime
labels or fitted market-state classifier are used. Every score and allocator
checks regime and feature cutoffs. Risk parameters live in a validated versioned
policy. Allocations are long-only, capped and unlevered; a conservative
correlation=+1 volatility upper bound avoids noisy covariance optimization.
Optional pairwise correlation screening fails closed when correlations are unknown.

Keep the existing RiskEngine, reconciliation, OrderPlanner, projected portfolio
validation, account freshness, quote certification, manual authority and paper
ownership boundaries. Unknown sectors are not guessed. `plan_paper_candidate`
only returns a review packet: approved sanitized PAPER_LEDGER input, exact
engine/policy/risk/cost-bound verified OOS records, and PIT metadata are required.
It cannot write a ledger or change the canonical strategy. No automatic switch
is added to `paper run`; review is an explicitly separate integration surface.

Daily SHADOW is opt-in through `policies/quant.yaml`; the shipped mode remains
`QUANT_V1_BASELINE`. The market service passes the same retrieved history to the
closure without a second network request. Challenger failures and invalid policy
are recorded separately from the baseline decision. Comparison records are
content-addressed and immutable, with public market/feature/policy/engine hashes,
pre/post-risk targets and turnover. No raw account snapshots are written by V2.
Any canonical report writes remain inside the existing approved host boundary.

The research simulator holds independent in-memory positions. Close signals
execute at the next session open, with explicit slippage/commission assumptions,
whole shares, cash, order, position, sector and turnover limits. It is not a broker
adapter or an alternative manual order planner. Missing outcomes fail evaluation;
NO_ACTION preserves shares. Buy-and-hold preserves shares. Mark-to-market constraint
drift is reported and does not authorize additional exposure. Prices, liquidity
and membership are not forward-filled. SPY frictionless tracking starts at the
first eligible open; a separate buy-and-hold control pays the same assumed costs.

Freeze experiment manifests before validation/test. Fixed thresholds and weights
are not fitted, so the training period supplies historical warmup. Walk-forward
tests have nonoverlapping test intervals and an explicit session embargo. Changed
parameters or engine code cannot reconsume the same financial OOS period in the
same registry. Synthetic diagnostics are permanently tagged and never evidence.
Engine identity hashes quant modules and reused risk/order/calendar/domain code,
normalized for Windows/Linux line endings.

## Alternatives and consequences

* No parallel broker/execution framework, LLM scoring, FinRL-X inference or
  high-dimensional sample-covariance optimizer is introduced.
* Relative momentum, short reversal, beta and drawdown are inspectable features;
  they are not automatically added to the main alpha blend without evidence.
* A0 reuses the original allocator. A1/A2 remain simpler alternatives to A3/A4;
  complexity carries no presumption of superiority.
* Unknown spread is explicitly unknown. Scores are not forecast returns. Cost
  benefit gating requires a separately supplied calibrated PIT improvement estimate;
  otherwise turnover/bands/cost estimates apply without inventing expected alpha.
* The public dataset currently fails adjustment and historical-availability
  certification. Engineering success therefore does not establish financial alpha.
* Statistical intervals use paired moving blocks and are descriptive pointwise
  intervals, not multiple-trial-corrected significance or a calculated PBO.

## Rollback and verification

Set `mode: QUANT_V1_BASELINE` (the default), or omit `quant.yaml`. V1 decisions,
orders and ledger schema are retained. Never reset the paper ledger. No broker
SDK, login capability, execution API or canonical migration is added.

Golden factors, future-price/regime/membership rejection, input completeness,
feed conflicts, missing bars/volume, constraints, costs, delayed fills, replay
determinism, immutable registries, source-bound evidence, daily noninterference,
paper-review isolation and rollback/default behavior are validated offline.
See the final acceptance and research report for actual completed checks.
