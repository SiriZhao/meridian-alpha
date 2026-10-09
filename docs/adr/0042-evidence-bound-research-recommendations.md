# ADR 0042 — Evidence-bound research recommendations

Status: Accepted for shadow research, 2026-10-09.

The terminal previously used V2.2 and classified eligible research as HOLD.
Live advisory copied model action labels into the displayed decision and used
V1 target weights as its position reference. Neither provided an auditable
V2.3 research decision. Account or model failure also hid useful Quant evidence.

Extend the existing terminal and live bridge. Preserve the frozen V1/V2.2/V2.3
numerical engines. A versioned ResearchRecommendation derives attraction from
eligibility and feasible exposure, independently of order permission. Embed it
in the existing additive DecisionBrief contract. Carry factor/source hashes,
cutoff, portfolio assumptions, model evidence and unknowns to the final report.

Account-free construction uses the existing engine's explicitly declared
100000 reference notional and empty reference holdings. It is not an account
balance. Monetary costs and actual eligible change remain unknown. Exposure
preferences are research model outputs, not calibrated expected returns.

Measured SMA20 ± ATR14/2 is a pullback diagnostic in adjusted-history units.
Its price basis is not certified identical to current raw execution prices.
It never supplies OrderPlanner limits and never proves intrinsic value.

PaperReviewRequest passes an explicit sanctioned in-memory Schwab-Paper
snapshot, certified execution observations and separately sourced planner
inputs through existing account, session, risk, reconciliation, order and
projected-portfolio gates. Check no-sell fills and declared friction as well.
Its ManualOrderTicket is BLOCKED or PAPER_ONLY. No new issuer of production
manual authority, ledger writer, fill simulator or broker adapter is added.
The existing seven-gate sealed manual authority remains mandatory for real
manual tickets; promotion and human authorization remain separate reviews.

The native four roles consume hash-bound numerical evidence including V2.3
targets. Model interpretations cannot modify scores, ranks or weights. Exact
numerical grounding applies to final symbol prose too. Failure retains Quant,
and disagreement stays visible. Fixture calls never prove real GPT acceptance.

The launcher selects V2.3_SHADOW explicitly. Direct legacy Python/MCP requests
retain their V2.2 default for reproducible baseline comparisons. Canonical
production remains QUANT_V1_BASELINE. No stacked PR base is changed.
