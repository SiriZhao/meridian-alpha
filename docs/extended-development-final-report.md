# Meridian Alpha — Extended development final report

## Scope and safety

Gate 5B/5C/5D was completed as a shadow/replay convergence pass. No Schwab
connection, broker surface, real account, real order, or automatic model
promotion was added. Known P0 remains zero.

## Certified intelligence

The existing Gate 3B.13/3B.14 path has real SEC PIT-certified fundamental
artifacts for AAPL, NVDA, and MSFT, and Gate 3B.11/3B.12 has two real
DeepSeek structured responses that passed parsing and citation authorization.
Both returned `NEUTRAL` at `0.5`, so the bounded live LLM modifier is `0`.
This is a valid neutral result, not a forced directional outcome.

The response replay path consumes sanitized, hashed structured output and does
not call DeepSeek. CertifiedAgentSignal issuance remains behind
`EvidenceAuthorizationService`; raw `AgentSignal`, unverified Yahoo evidence,
TradingAgents output, synthetic evidence, and dislocation assessments cannot
enter Alpha Fusion. Base research, dislocation, and combined modifiers retain
the deterministic `0.18`, `0.10`, and `0.20` caps respectively.

## FinRL-X challenger

Meridian exposes only a vendor-free, side-effect-free allocator protocol. A
validated manifest is required, artifact bytes are checked against their
SHA-256 immediately before inference, and the optional runtime receives a
frozen PIT feature snapshot plus account ID/hash and policy constraints. Target
weights are checked against the validated universe and policy bounds. Runtime
errors and invalid artifacts fail closed. No FinRL-X package or validated model
artifact is installed, no shadow inference was run, and promotion is false.

The challenger comparison reports observable target-weight stability only.
Return, volatility, Sharpe, drawdown, and transaction-cost fields remain null
when no OOS evidence exists; no performance is fabricated.

## Reproducibility and reliability

`FrozenFeature` rejects future availability, non-SHA-256 source hashes, and
non-finite values. `AnalysisRunManifest` records code, account, security
master, market, fundamental, evidence, LLM, policy, feature, allocator, and
challenger identities. `ReplaySafeObservationCache` preserves the original
`available_at` and source hash, rejects historical rewrites, and rejects
sensitive cache keys/values.

The offline soak covers stale/partial accounts, provider failures, invalid or
abstaining LLM output, future evidence/quotes, duplicate snapshots, external
trades/partial fills, dislocation rejection, unavailable challenger runtime,
and replay determinism. All failures remain explicit and fail closed.

## Readiness

- Host contract: implemented; no real Host envelope was supplied. Status is
  `READY_FOR_SUPERVISED_HOST_INPUT`.
- Execution quote: `TO_BE_SELECTED`; Yahoo is last-only research shadow and is
  not execution-grade. Manual entry is therefore `NO`.
- Security master: 11 bounded records exist, but authoritative primary
  provenance is `0/11`; no enum-only promotion was performed.
- News and macro remain unverified/configuration-unavailable and cannot enter
  `CertifiedEvidenceView`.
- TradingAgents remains qualitative/second-opinion context only.

## Final labels

Legitimate labels for this checkpoint are:

- `CERTIFIED_FUNDAMENTAL_PIPELINE_READY`
- `READY_FOR_SUPERVISED_HOST_INPUT`
- `READY_FOR_LONGER_SHADOW_OBSERVATION`

`FINRLX_SHADOW_CHALLENGER_READY` is not claimed because no validated artifact
or runtime exists. `REAL_LLM_ALPHA_BREAKTHROUGH` is not claimed because both
real responses were neutral and produced no non-zero modifier.

## Validation and artifacts

The project virtual environment passes the full test, Ruff, Pyright, and diff
checks. Safe review files are generated under `artifacts/` by
`scripts/package_review.ps1`; excluded environment, cache, credential, and
runtime files are not packaged.

No broker writes were implemented. Schwab is not connected. Real orders: zero.
