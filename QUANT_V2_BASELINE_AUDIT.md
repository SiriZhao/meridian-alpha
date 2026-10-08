# Quant V2 baseline audit — 2026-10-08

## Repository and scope

Origin: `https://github.com/SiriZhao/meridian-alpha.git`. Development starts from
`origin/main` (`1d7e064`), then fast-forwards the already published canonical
hardening branch to `414d869`. The original checkout remains on
`feature/forward-evidence-alpha-lab-20261008`. Its five modified tracked files
and two untracked modules are preserved and excluded from this delivery.
These pending changes add attribution and reviewed dated-close evaluation.
During this task they were published as `09e95dd` on the prior feature branch;
the published commits were subsequently merged into the isolated V2 branch.
Further uncommitted changes in the original checkout remain excluded. The final
validation therefore includes the published Phase 4 attribution/forward tests.

## Existing algorithms

* `daily_closure.py`: after account/quote freshness gates, each configured
  symbol gets `max(0, daily_return)`, confidence=1, evidence_quality=1.
  These constants describe plumbing, not forecast calibration. Qualitative
  daily research is stored as advisory context and does not size this path.
* `candidates.py`: deterministic, budget-bounded research candidate selection;
  feature timestamps and risk flags limit eligibility. It is a research
  scheduler, not the daily portfolio allocator.
* `alpha_fusion.py`: the separate certified-research route combines bounded
  technical and certified qualitative components. Keep its contracts intact;
  Quant V2 scores have no LLM contribution.
* `allocation.py`: sort positive evidence-bearing scores, select the position
  limit, proportionally allocate available cash, independently cap positions,
  round down to 1e-6. Unallocated cap overflow remains cash. FinRL-X is an
  explicit unavailable optional adapter, never a fabricated inference.
* `risk.py`: deterministic position/sector/cash constraints. Unknown equity
  sector metadata is rejected when sector constraints require it. The daily
  operational path's unclassified grouping is not PIT sector certification.
* `orders.py`: reconcile approved targets; sell drafts first, whole shares,
  conservative buy cash without assuming sale fills, spread/gap/freshness,
  minimum notional, order and turnover caps, projected portfolio validation.
  This is the only manual order planner; V2 must reuse it.
* `research_backtest.py`: isolated symbol/horizon directional evaluation of
  research. It is explicitly not a portfolio simulator and cannot establish
  portfolio CAGR, costs or execution timing.
* `historical.py`: project-owned OHLCV/identity/calendar/availability contracts.
  Public historical retrieval retains retrieval-time availability and remains
  unverified. RAW and adjusted research bars are never execution quotes.
  `stable_id` identifies a row but does not hash its price values: V2 feature
  lineage must hash the actual eligible bar content.
* `research_universe.py`: resource-aware research workload reduction, not a
  historically reconstructed investable universe.
* `shadow_evaluation.py`: evidence grounding, repeatability and quality of
  advisory research; not evidence that a trading alpha works.
* `forward_evidence.py`: immutable shadow predictions, matured provenance-bound
  outcomes, calendar horizons, no automatic promotion. Symbol/horizon rows
  overlap and must not be treated as independent portfolio observations.

## Prior safety repairs retained

`canonical_run.py` seals one report truth and checks projections. Provider
resilience preserves discrepancy and quality diagnostics. Runtime/report
publication uses staged bundles and atomic ownership. Paper lifecycle checks
the canonical day before research and rechecks ownership transactionally.
Committed provider, canonical and persistence regressions remain in the full
suite. No runtime migrations, canonical writes or ledger resets are needed.

## V2 replacement boundary

Add versioned PIT features, deterministic factor composition and regimes,
constrained allocation and friction-aware target decisions. Wire these into
an opt-in daily shadow surface and an explicitly approved paper review surface.
V1 remains the default and rollback. Reuse domain target models, RiskEngine,
ReconciliationEngine, OrderPlanner and ProjectedPortfolioValidator. Do not
replace quote certification, account freshness, canonical ownership, report
sealing, research certification, manual authority or paper persistence.

## Research acceptance

No certified, historically available, corporate-action-covered and membership-
dated multi-year dataset exists in the repository. Public histories fetched
today cannot be backdated. Synthetic diagnostic replays may prove timing and
invariants, but cannot prove investment performance. A1–A4 and A0 must share
the same data, execution delay and cost conventions in any empirical claim.
All thresholds and weights are specified before evaluation; final OOS is not
a tuning surface. Unknown fundamentals, sectors or spread stay unknown.

Baseline validation evidence is recorded in `docs/quant-v2/ACCEPTANCE.md` when
the complete run finishes; historical test totals are not current evidence.
