# Quant V2.3 engineering acceptance

Numerical engine: `7d85f0ba5fb84fd574d548cd71fe2ef45d60922b7efbd298ec3a9ef24228952e`.
Frozen V2.2 dependency: `e510e84d05b227e2ed2333ff886d4906ecd7a80ac4e5b925c964e91567df821c`.
Development branch: `codex/flagship-quant-20261009`, based on PR6 research terminal.

* Recovered baseline full repository validator: PASS, Windows 1035 pytest.
* Final synthetic registry: PASS, 22 fixed variants × 2 folds × 2 partitions =
  88 evaluations; 92 archive members, metrics/identity/authority checks PASS.
* Public history acquisition: SPY/QQQM/AAPL/MSFT/NVDA, five descriptive references,
  zero provider failures; no PIT/execution certification or financial alpha claim.
* Quant regressions: 43 PASS; configuration/packaging repair: 6 PASS.
* Final full source validator on code `ec28d78`: PASS, 1079 tests, 421.60s.
  Ruff, Pyright, dependency integrity, all original/new archives, terminal
  contracts, CLI and isolated safe-paper acceptance PASS.
* Independent GitHub clone on `ec28d78`: Python3.12 frozen lock/import identity
  PASS; full validator PASS, 1079 tests, 523.11s. Numerical engine hash identical.
* Windows/Linux CI on `ec28d78`: push [37869337550](https://github.com/SiriZhao/meridian-alpha/actions/runs/37869337550)
  and PR [37869341809](https://github.com/SiriZhao/meridian-alpha/actions/runs/37869341809)
  SUCCESS. Windows 1079; Linux 1077 plus 2 platform skips. Manual-authority
  negatives 21 and replay-integrity regressions 8 PASS on both platforms.
* Production default V1, original V2.1/V2.2 archives and policies: unchanged.
* Canonical runtime/database/ledger: not accessed. Broker submission DISABLED;
  no real-account/broker methods, no migrations/resets, no automatic promotion.

Status: ENGINEERING_COMPLETE, SYNTHETIC_VALIDATION_COMPLETE,
REAL_FINANCIAL_VALIDATION_PENDING, ALPHA_NOT_YET_DEMONSTRATED.
Neither 88 synthetic evaluations nor public survivor references demonstrate
future cost-adjusted alpha. Covariance/conditional budgets are ex-ante target
assumptions; no guarantee is made about unfilled orders, future beta or tails.

Remaining evidence blockers: reviewed PIT adjusted histories and revisions,
corporate-action cash/share semantics, historical membership/delistings,
sector/ETF metadata, historical calendar, observed spreads, independent
expected-return calibration. Recovery uses the exact checkpoint and immutable
plan/archive, not re-fitting the final test.

Delivery commits: `dec9674` (algorithm/evidence/schema integration), `ec28d78`
(offline source packaging regression repair), followed by acceptance documents.
Draft PR [#7](https://github.com/SiriZhao/meridian-alpha/pull/7), stacked on
`codex/research-terminal`; no other PR base changed and no main merge.

Local logs and raw public responses remain in the isolated worktree `.tmp`.
`verification.json` contains only reviewed counts, hashes, paths and safety
statuses, not host/account dumps. `source-fingerprints.json` pins new source
files; `.gitattributes` preserves their content-bound bytes across platforms.
Start a fresh Python process after any source edit; never edit a frozen running
experiment. Experiment registration checks source before/after each replay.

No positive financial conclusion follows from engineering completion. The
slightly smaller fixture loss is accompanied by lower exposure; regime budgets
added no observed value in that fixture. Real V1/V2.2/V2.3 cost-adjusted OOS
comparison is MISSING_EVIDENCE, not a successful alpha upgrade.
