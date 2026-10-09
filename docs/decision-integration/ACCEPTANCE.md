# Decision integration acceptance

Financial status: ALPHA_NOT_YET_DEMONSTRATED. No real market session, actual GPT
invocation, broker side effect or canonical account mutation was performed.

Recovery base bc25ebe was clean and remote-matched. The prior 1079-test baseline
and successful PR7 Windows/Linux CI were verified. Targeted baseline 84 PASS.

Initial integration 1ca3ab42e014b45fd8afcb3b14bef2e43c2b794a passed the full
source validator (1104 tests, 275.04s) and independent clone (1104 tests,
261.91s), including Ruff, Pyright, frozen Quant archives, terminal schemas,
CLI and isolated paper acceptance. These are superseded engineering checks,
not acceptance of the final implementation: subsequent stronger assertions
found a display/source mismatch.

Preserved defects and fixes:

- Initial V2.3 launcher selection broke an existing V2.2 fixture contract.
  Retained the explicit legacy direct-call baseline; launcher selects V2.3.
- Workflow shortlist substitution invalidated reuse of an existing Quant fact
  receipt. Preserved the original workflow's receipt identity and regression.
- Fresh clone initially used an unsupported lock extra; corrected to documented
  uv sync --frozen --group dev. Failed setup log was retained.
- A new Skill link escaped its portable package. Replaced it with an existing
  packaged reference; standalone extracted-package validator passed, 12 files.
- Live comparison/report/GPT evidence still read some V2.2 scores despite a
  valid V2.3 packet. SPY is a benchmark, not a V2.3 candidate, so the cross-section
  differs. Added exact per-symbol score assertions, reproduced three failures
  in .tmp/decision-score-mismatch.log, then bound all three surfaces to the
  actual flagship scores/targets. This did not alter algorithm coefficients.

Corrected targeted suite: 102 PASS; extra final live source correspondence
checks 3 PASS. Full corrected-source/clone and final CI are pending at this
checkpoint; subsequent delivery evidence must name their actual SHA.

The unchanged frozen V2.2 engine hash is
e510e84d05b227e2ed2333ff886d4906ecd7a80ac4e5b925c964e91567df821c;
V2.3 numerical engine remains
7d85f0ba5fb84fd574d548cd71fe2ef45d60922b7efbd298ec3a9ef24228952e.
Its sealed 88-run diagnostic archive remains valid and untouched.

Engineering fixtures cover qualified candidate and no-signal states, no
account, stale price, Quant/GPT conflict, timeout/quota failure, missing history,
cash infeasibility, holdings vs target, closed market, risk/metadata failure,
all-NO_ACTION behavior, measured zones, exact evidence IDs, pure PAPER_ONLY
draft planning, JSON/Chinese report, MCP/CLI and golden repeatability.

Real financial PIT history, corporate-action/price-basis qualification,
calibrated net expected return, licensed execution feeds and independent
live/native-model acceptance remain blockers. V1 canonical stays unchanged;
V2.2 remains available as a research baseline; V2.3 has no automatic promotion.
Paper planning creates no ledger transactions and cannot issue production
seven-gate manual readiness certificates. Real orders still need human approval.
