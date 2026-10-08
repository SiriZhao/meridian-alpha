# 2026-10-08 live acceptance: evidence classification repair

Candidate `c7b330c3c954592d3d19fa205baacfc84d070f6c` was frozen on
`codex/quant-live-bridge` before canonical access. Python 3.12.10, the frozen
dependency environment, package origin, all policy hashes and Quant engine hash
were verified. Quant coefficients were not changed during acceptance.

Two actual public-market observations completed at 11:28:44 and 11:35:36
America/New_York, within the regular session. They were not fixtures. Yahoo
future timestamps were rejected; Nasdaq fallback preserved the failures. The
second observation obtained fresh reference prices for AAPL, MSFT, NVDA and
SPY. Feed delay and execution entitlement remained unknown. The Quant bridge
qualification gates and completed-session raw OHLCV diagnostics executed, but
**the full V2.2 score did not execute**: qualified PIT/corporate-action evidence
was insufficient. Scores, ranks, regime and targets remained unknown. This is
partial research, not verified financial evaluation or OOS evidence.

Doctor passed. Exactly one canonical Schwab-Paper day ran:
`daily-ff9a368c3590e82545aad681`, `PAPER_NO_TRADE`, zero orders and fills.
Cash/positions/transaction-version fingerprints were unchanged. Daily ownership,
NAV-mark and research/audit records were legitimately added, so the database
itself was not unchanged. The completed day must not be repeated to manufacture
independent samples. Broker submission, manual execution readiness and quote
certification remained disabled/blocked; V1 remained canonical.

The canonical V1 native GPT shared invocation succeeded in 20.660 seconds of a
180-second budget. All four logical roles used `gpt-5.6-luna`/`low`, passed schema
validation and referenced supplied evidence IDs. This was one model invocation,
not four independent trials. It did not consume V2.2 live evidence and does not
qualify the external ordinary-terminal live-advisory acceptance. Existing model
scenario weights are uncalibrated; no measured financial probabilities or alpha
are inferred from them.

Inspection found a defect: without `quant_live`, the native adapter labeled
`PublicResearchObservation` prices and daily-return transforms `VERIFIED`.
Canonical ownership and freshness do not provide such certification. The
candidate was sealed as **LIVE_RESEARCH_DEGRADED** before repair. Three regression
cases (LIVE, FIXTURE, REPLAY) reproduced the defect. The repair marks these public
inputs and their transforms `UNVERIFIED` regardless of optional Quant bridge
presence. Verified-evidence coverage no longer counts them. V1 deterministic
scores, sizing, orders, policies and hard safety gates are unchanged.

Original sanitized evidence is retained outside Git at:
`E:\MeridianAlphaRuntime\reports\live-acceptance\2026-10-08\acceptance-8d89c3b42b9841caaa7b44bbc17b92af`.
It contains immutable observations, quote/history hashes, comparison packets,
sanitized native invocation metadata, paper result, ledger proofs, blockers,
outcome, manifest and a recoverable checkpoint. No raw account snapshot or model
prompt was copied into this acceptance tree. Local orchestration resides in
ignored `.tmp/mission3`; observation monitoring has stopped.

The original frozen candidate passed its existing full platform CI (Windows
992; Linux 990 + 2 skips). An additional isolated group passed 79 tests in the
approved host. The restricted sandbox run had 78 passes and one child-process
timeout failure (60-second pipe closure); its failure was preserved. The same
test passed in the approved host in 5.20 seconds; no production timeout change
was justified. New repair validation and publication belong to a separate SHA.

Next: validate and publish this repair, freeze the new candidate, restart only
read-only regular-session observation and live advisory. Preserve the completed
paper day and distinguish its old SHA. GPT/live-advisory acceptance must be
launched by an operator from an ordinary Windows PowerShell outside Codex
ancestry. Use `scripts/run_live_advisory.ps1` with the correct checkout and runtime;
do not reuse stale quotes as live inputs or legacy hardcoded role fixtures as
financial evidence. No automatic main merge or strategy promotion is authorized.

The repair passed `scripts/validate_repo.py` on approved Windows host with
isolated runtime/cache: **995 tests in 213.84 seconds**, dependency integrity,
Ruff, Pyright, V2/V2.2 archived experiment reproducibility, CLI smoke and safe
paper acceptance. Targeted validation passed 33 tests. The safe-paper fixtures
are engineering regressions and are separate from the actual canonical paper
day described above. Publication and new live evidence are subsequent checkpoints.
