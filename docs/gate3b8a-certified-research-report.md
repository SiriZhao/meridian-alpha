# Gate 3B.8A certified research report

## Implemented safety hardening

- Host account normalization now uses system UTC for production validation.
  A supplied historical clock is accepted only with explicit `replay=True`.
  Future as-of/retrieval times reject; an old snapshot remains stale even when
  its old retrieved timestamp is nearby.
- Dislocation modifiers now require a sealed `CertifiedDislocationAssessment`
  issued from the exact `CertifiedEvidenceView`; arbitrary evidence cannot
  authorize a modifier.
- SEC accession metadata has a project-owned contract and pure adapter that
  can promote an exact Company Facts accession only when authoritative
  acceptance metadata is present and no later than the decision cutoff.

## Certification posture

The SEC adapter deliberately does not replace the existing Company Facts path.
It is a distinct future provider path. Missing acceptance metadata, a mismatch,
or an acceptance timestamp after the cutoff yields no certified item.

No SEC network accession metadata was acquired during this run, so real
certified evidence count is zero. No DeepSeek or TradingAgents request was
made. This avoids promoting a provider based on an unverified timestamp.

## Validation

- 173 tests passed.
- Ruff passed.
- Pyright passed.
- `git diff --check` passed.

## Status

- HOST CLOCK: PASS
- DISLOCATION CERTIFICATION: PASS
- SEC ACCESSION JOIN: IMPLEMENTED / TESTED (offline contract)
- SEC ACCEPTANCE TIME: NOT YET ACQUIRED FROM AUTHORITATIVE RESPONSE
- SEC PIT CERTIFIED: NO REAL OBSERVATION
- SECURITY MASTER AUTHORITATIVE: 0/11 newly promoted this run
- REAL CERTIFIED EVIDENCE COUNT: 0
- LIVE DEEPSEEK: SKIPPED (precondition unmet)
- REAL CERTIFIED SIGNAL COUNT: 0
- FIRST REAL NON-ZERO LLM ALPHA: NOT ATTEMPTED
- KNOWN P0: none
- KNOWN P1: acceptance metadata retrieval/join, authoritative identity
  provenance, execution quote authority, and broader provider certification.