# Gate 3B.9 final report

## Real certification result

The distinct `sec-edgar-accession-certified` provider path is now capable of
emitting `CERTIFIED_HISTORICAL_PIT` only after a Company Facts accession is
joined exactly to a SEC submissions acceptance timestamp. Bounded live SEC
validation produced two such observations: AAPL and NVDA. Yahoo remains
unverified context and cannot enter the certified grounding input.

## Live LLM result

A local DeepSeek key was present, but `policies/models.yaml` explicitly sets
`research.live_enabled: false`. No configuration or secret value was altered
or read, so live DeepSeek was skipped. This prevents a real
`CertifiedAgentSignal` and non-zero live-LLM alpha in this gate.

## Host and execution posture

Host fixture tests retain fresh-complete analysis allowance, stale blocking,
partial analysis-only behavior, and future timestamp rejection. Execution
quotes remain `TO_BE_SELECTED`; Yahoo is last-only and non-execution-grade.

## Status

- Pytest: 177 passed.
- Ruff: pass.
- Pyright: pass.
- Real PIT-certified SEC items: 2.
- Real certified evidence count: 2.
- Real CertifiedAgentSignal count: 0.
- FinRL-X runtime: MODEL_UNAVAILABLE.
- Broker / Schwab / real account / real orders: none.

Release state: `READY_FOR_MORE_CERTIFICATION_WORK`.