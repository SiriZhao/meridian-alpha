# Gate 3B.10 final report

## Live-shadow enablement

The checked-in research policy remains `live_enabled: false`. Gate 3B.10 adds
an ephemeral `LiveResearchShadowOptIn(enabled=True)` that produces a runtime
settings copy only for a caller explicitly requesting `LIVE_SHADOW`. TEST,
REPLAY, and ordinary daily behavior remain off. The live normalizer boundary
accepts only a sealed `CertifiedEvidenceView`.

## Bounded live attempt

Two calls were budgeted for AAPL/NVDA, whose SEC evidence views each contained
one real `CERTIFIED_HISTORICAL_PIT` accession-certified item. The process
returned no sanitized structured payload. The result is fail-closed as
inconclusive: no available/neutral result was fabricated, no
`CertifiedAgentSignal` was issued, and no alpha modifier was applied. No retry
was made.

## Status

- Pytest: 179 passed.
- Ruff / Pyright / diff check: pass.
- Real PIT-certified evidence: 2 (AAPL, NVDA).
- Live DeepSeek: INCONCLUSIVE; two-call budget exhausted.
- Real grounded signals / CertifiedAgentSignals: 0 / 0.
- First real non-zero LLM alpha: no.
- Host finance smoke readiness: retained for a future supervised data test;
  manual entry remains impossible without execution-grade quotes.
- FinRL-X: not promoted; runtime MODEL_UNAVAILABLE.
- Broker / Schwab / real account / real orders: none.

Release state: `READY_FOR_LIVE_LLM_RETRY` after diagnosis of the missing
sanitized response payload. No certification rule was weakened.