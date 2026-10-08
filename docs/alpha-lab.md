# Isolated alpha laboratory

Implemented: deterministic score challengers, reviewed close receipts, immutable
isolated outcome ingestion, read-only reconciliation, purged paired signal
evaluation and canonical decision attribution. Not implemented: an authenticated
review service, automatic qualified close acquisition, full portfolio
walk-forward simulator, native-role ablation datasets or production promotion.

The operational score remains `max(0, daily_return)` with confidence 1. GPT
consultation does not change this score or target. Allocation caps individual
weights without redistributing unused capacity; the operational risk overlay
groups symbols as `OPERATIONAL_UNCLASSIFIED`, which can constrain aggregate
exposure. Actual no-trade reasons come from `decision_attribution`, including
incomplete limit-price inputs, minimum notional, whole-share rounding, cash
reserve, missing quote, risk caps or failed projected portfolio validation.
This does not establish which reason dominated historical canonical days.

## Read-only commands

Use project Python. These commands do not initialize a runtime, create an
account, download data or invoke an LLM:

```powershell
.\.venv\Scripts\python.exe -m meridian.alpha_lab score --input .tmp/alpha-lab/input.json
.\.venv\Scripts\python.exe -m meridian.alpha_lab reconcile --input .tmp/alpha-lab/forward.json --closes .tmp/alpha-lab/closes.json --as-of 2026-10-08T20:00:00+00:00
```

`score` accepts `LabInput`; `reconcile` reads an existing v1/v2 `ForwardLedger`
and optional reviewed-close archive. A missing specified input is an error;
missing outcome evidence remains pending/missing. `forward-status` remains the
canonical read-only compatibility command. Never use canonical paper runs to
create lab samples or bypass public quote certification.

## Python interfaces and trust

`dated_close.evaluate_close` returns a typed quality result with no returns for
unverified evidence. `ingest_reviewed_outcome` requires an existing frozen
prediction in an isolated forward ledger beneath a directory named `alpha-lab`;
canonical runtime paths are rejected after resolution. `append_reviewed_pair`
creates a separate immutable receipt archive. Readers check schema, identity,
digests and exact maturity/benchmark alignment. Locks fail visibly on contention;
retry after ownership is released. There is no automatic retry storm.

Reviewer references should be non-sensitive audit IDs. A receipt is a local
human attestation, not proof that an arbitrary provider is official. Review
both inception and terminal unadjusted prices and all asset/benchmark actions.
Synthetic records must retain `SYNTHETIC_FIXTURE`; do not relabel them as real.
No raw account, credential, production ledger or broker identifier is required.

`lab_evaluation.evaluate_signals` reports cross-sectional signal metrics and
non-overlapping temporal blocks. Minimum 20 rows in the legacy policy is not 20
independent decisions or evidence of alpha. No usable cost/slippage/fill model
means portfolio metrics are `NOT_EVALUABLE`. No certified research means the
Quant+LLM contribution is zero and comparison evidence is insufficient.

## Fixed recipe V1

Cash score 0. Operational score `max(0, daily_return)` exactly. Multi-factor uses
21 consecutive defined session closes available by cutoff, reviewed consistent
adjustment basis, and fixed weights: .4 momentum over 20 intervals, .3 price
relative to arithmetic mean, .2 drawdown from maximum, minus .1 population
volatility of those 20 returns. Output is bounded to [-1,1]. Missing history
returns no score. Quant+certified LLM adds the existing bounded research modifier
to the operational score and bounds the result to [-1,1]. This different recipe
is explicitly experimental and does not claim to replicate the operational
allocator, execute a portfolio or contain validated alpha.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_alpha_lab.py -q
.\.venv\Scripts\python.exe scripts/validate_repo.py
```

Offline safe acceptance uses a declared fixed OPEN-session clock scoped to its
fixture harness. The production clock and market gates are unchanged. Workspace
temporary directories avoid Windows sandbox temp-directory ACL failures.
