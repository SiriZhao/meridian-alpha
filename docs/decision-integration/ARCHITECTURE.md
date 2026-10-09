# Decision integration audit and implementation

Base: bc25ebeab9c6b1dde02da9e0ca0ec35ed8ce2271, branch
codex/flagship-quant-20261009. Clean local/remote recovery; PR7 remains draft
over codex/research-terminal. Prior full validation 1079 Windows tests is a
baseline, not this change's acceptance.

| Function / contract | Baseline gap | Implemented connection |
|---|---|---|
| research_terminal.quant_terminal_snapshot | V2.2 only | Explicit V2.3 selection calls build_flagship_packet; retains V2.2 comparison packet |
| TerminalPlanner.build | Eligible rows uniformly HOLD | Deterministic attraction, feasible exposure, reasons and next inputs |
| terminal_model_context / GPTNativeResearchOrchestrator._evidence | Targets absent from numerical evidence | Hash-bound V2.3 attribution and desired/feasible weights; separate signal and portfolio policy identities |
| generate_decision_brief | Global waiting reason | Per-symbol ResearchRecommendation, ResearchPricePlan and trace, exact evidence correspondence |
| LiveAdvisoryService._run | GPT labels drive research category; V1 guidance | Supported launcher explicitly selects V2.3; deterministic category and target guidance, GPT opinion separate |
| live_quant_bridge | V2.2 qualified lane only | Versioned V2.3 packet on same cutoff; no downgrade of public history into PIT |
| live_report / render_decision_brief | Large JSON embedded in prose | Chinese overview, shortlist, attribution, argument, conditions, blockers and next inputs; complete JSON retained |
| plan_paper_review | No V2.3 handoff | Existing RiskEngine → ReconciliationEngine → OrderPlanner → full/partial-fill ProjectedPortfolioValidator; no ledger writes |
| MCP / CLI | Quant-only view | Typed bounded decision_research_brief and research_paper_plan; explicit input-file CLI workflow |

The six-factor scoring, covariance/turnover construction, frozen policy,
V2.1/V2.2/V2.3 archives, daily_closure operational scoring, risk.py, orders.py,
reconciliation.py and production account workflow are unchanged. No provider,
state store, forecasting model or parallel order engine is introduced.

Attraction categories reflect policy eligibility and risk allocation, not
probability of profit. BUY_CANDIDATE is account-independent. A measured price
plan produces ACCUMULATE_CONDITIONALLY, not an instruction to buy immediately.
HOLD requires supplied valid current weights within the research band; TRIM
and EXIT_REVIEW require actual supplied exposure. NO_ACTION reflects signal
exclusion or zero risk budget. Missing evidence has explicit diagnostics.

Company names remain unknown when the current security master has no verified
legal name. Historical membership/sector/ETF overlap are not guessed. Public
raw diagnostics reuse the existing within-session lane and never gain ranks.

The original four-role chain remains responsible for explanations and
adversarial research. Universe-level interpretation is labeled as such; it is
not silently converted into symbol-specific catalysts. Price probabilities,
expected returns and financial predictive confidence remain uncalibrated.
The additional existing live symbol interpretation is advisory only, with
evidence IDs and numerical correspondence enforced. Prior-cutoff research
remains dated when the live quote refresh advances the information snapshot.

Actual account-bound paper targets are recomputed with current weights/NAV.
The account-free reference target is not silently used to size real shares.
Paper input is opt-in and in-memory; raw snapshots are excluded from request
dumps. Drafts are NOT_EXECUTED. No canonical initialization/reset/migration,
broker credentials, HSBC access or brokerage methods exist in this addition.
