# ADR 0038: Separate challenger signal, risk, friction and manual review

Date: 2026-10-08. Status: accepted for SHADOW_ONLY engineering, not promotion.

V2.1 mixes signal and security/regime risk factors in a bounded score before
portfolio risk sizing. Its archived results remain valid historical records,
but are synthetic engineering evidence rather than demonstrated alpha.

Add a composed ChallengerPolicy and new typed observations/score/packet beside
the unchanged V2.1 contracts, inside existing quant modules. Reuse PIT feature
validation, the existing event-driven runner, RiskEngine, ReconciliationEngine,
OrderPlanner and ProjectedPortfolioValidator. Keep QUANT_V1_BASELINE and the
existing policy file unchanged. The new policy has SHADOW_ONLY authority and
cannot configure a canonical or paper switch.

Predictive strength contains fixed absolute/relative/trend weights. Volatility
and market state are reported as risk transformations and applied once as
portfolio ceilings. Missing factors keep their weights; tied-rank blending has
a bounded contribution and explicit residual discontinuity. Correlation
components receive proportional caps; missing/invalid covariance stays unknown.
No unconstrained optimizer or inferred ETF/sector classification is introduced.

An external calibrated expected-return estimate must bind its horizon, training
label availability, feature fingerprint and actual post-friction proposal.
Without it, benefit is unknown. Fundamentals have release, fiscal and revision
contracts, but the adapter remains disabled. No live data, provider SDK or LLM
gets authority to invent these inputs.

Research packets contain exposure layers and hypothetical eligible changes,
never trade authorization. Missing accounts remain unknown. Quote, freshness,
metadata and projected-risk checks remain mandatory. A no-sell/all-buy scenario
prevents relying on recommended sales as fills. Packets do not persist raw
snapshots or grant any brokerage capability.

The new plan/registry and additive schemas are versioned independently; original
V2.1 schemas, plans, ZIP and results are unchanged. Exact V2.1 replay uses pinned
commit 4664cb4. Fixed-budget neutral-factor ablations distinguish nominal target
matching from realized whole-share/partial-fill exposure. Financial conclusions
remain pending independently qualified PIT/action/membership/calendar data.
