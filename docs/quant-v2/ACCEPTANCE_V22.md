# Quant V2.2 acceptance — 2026-10-08

Historical acceptance at 5bdb7a4 follows. Resumed review identified missing
correlation/unknown-covariance guards for partial fills and unknown-sector
classification; final mission acceptance is pending those corrections.

ENGINEERING_COMPLETE
SYNTHETIC_VALIDATION_COMPLETE
REAL_FINANCIAL_VALIDATION_PENDING
ALPHA_NOT_YET_DEMONSTRATED

## Executed engineering evidence

Final code commit `5bdb7a4408ab01ae5d712fb8af9196ab38701a7d`, branch
`codex/quant-engine-v2`. Implementation: `c5dc594`; immutable registry and
acceptance tooling: `904f8d6`; installable contract correction: `5bdb7a4`.
Production policy and hard risk/execution/reconciliation modules are unchanged
relative to starting `4664cb4`. Frozen lock is unchanged. Main was not merged.

| Check | Observed result |
|---|---|
| Targeted starting baseline | 135 passed, 91.07s |
| Combined targeted acceptance | 165 passed, 103.65s |
| Approved-host full validation | 955 passed, 192.81s; all remaining gates PASS |
| Independent GitHub clone, final code | 955 passed, 211.15s; all remaining gates PASS |
| Final code Windows push CI | 955 passed, 151.81s |
| Final code Ubuntu push CI | 953 passed, two Windows-only skips, 240.83s |
| Manual authority negatives / replay integrity | 21 / eight passed on both CI platforms |
| V2.2 contracts / archive | Seven contracts / 82 JSON members / 76 complete evaluations PASS |
| Original V2.1 archive reproduction | Pinned independent clone, 92 evaluations / 88 payloads exactly matched |
| New V2.2 archive reproduction | Independent final-code clone, 76 payloads and summary exactly matched |
| Installable wheel | Seven contracts, two policies, eight checked Quant modules match source |

Restricted Windows full validation recorded 954 passed and one failure in the
existing native child-tree timeout cleanup test. The same unchanged test passed
under approved host execution, independent clone and Windows CI. No risk tests
were removed, skipped or relaxed. Ubuntu's only skips are the Windows PowerShell
5 launcher and Windows-only review packaging; no Quant skips or xfails.

[Push CI](https://github.com/SiriZhao/meridian-alpha/actions/runs/37769709023)
and [PR CI](https://github.com/SiriZhao/meridian-alpha/actions/runs/37769716277)
both SUCCESS for the final code SHA. Dependencies, Ruff, Pyright, old/new
artifact validation, CLI help, skill packaging and credential-pattern scan all
passed. Independent clone uses its own Python 3.12.10 environment synchronized
from the checked-in frozen lock; interpreter and imports were checked inside
the clone. Windows source-review packaging passed CI.

## Research interpretation and blockers

All new observations are SYNTHETIC_DIAGNOSTIC: six labeled fixture series, 420
bars each, five candidates, two chronological folds. Parameters and definitions
were sealed before replay; no winner selection, training or final financial
OOS fitting occurred. V22's fold-1 net return is negative, cost stress worsens it,
and fold-2 does not trade. Active ablations have different actual exposure;
zero-exposure matches are uninformative. No predictive-alpha, cost-adjusted
outperformance, real market robustness or resolved survivorship claim follows.

Real evidence requires independently qualified adjustment vintages, corporate
actions, dated membership/sector/calendar coverage, delistings and authenticated
provenance. Expected return is uncalibrated, predictive confidence null,
fundamentals disabled, spread/ETF lookthrough/broad participation unknown.
Moving-block intervals remain short-sample, dependent, descriptive and pointwise.

## Runtime and safety

V22 extends existing feature/scoring/portfolio/replay modules; it is implemented
algorithm behavior, not solely an experiment file. `quant packet` delivers typed
Chinese research explanations and layered exposures for a future advisory bridge.
It reuses existing deterministic risk/reconciliation/order/projected validation,
including all-buy/no-sell scenarios. It does not connect a new live-advisory
route, activate canonical shadow automatically or authorize any candidate trade.

V1 remains the default. V2.2 policy is SHADOW_ONLY and cannot configure paper
promotion. Paper readiness remains INSUFFICIENT_EVIDENCE. Rollback means
continuing V1 and omitting the optional challenger/packet call; no ledger migration.
No canonical Doctor/paper run, runtime write, database reset, ledger migration,
account fabrication, broker credential or real broker side effect occurred.
Safe-paper acceptance used only disposable synthetic runtimes, exercising
NO_ACTION and one synthetic fill, duplicate prevention and report consistency.

Subsequent delivery commit contains only evidence/checkpoint files; the exact
remote tip and its own CI are verified at handoff. See the algorithm audit,
research report, frozen plan and checkpoint for formulas, parameters and commands.
