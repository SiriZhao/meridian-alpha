# Gate 3B.6 / 3B.7 night-run status

## Implemented and tested

- Gate 3B.5 is checkpointed locally at `15e41977b6619f2bad220e719fb8366ab94746a6`.
- `ResearchContextPacket` explicitly represents mixed-trust shadow context.
- Sealed `CertifiedEvidenceView` filters every item by ticker identity, explicit
  `available_at`, decision cutoff, closed PIT status, and matching provider
  capability certificate.
- In LIVE pipeline mode, a normalizer receives only the certified view packet;
  mixed context remains audit/shadow context and is never passed to it.
- Authorization uses that exact filtered packet, preserving its existing
  provider-by-provider capability enforcement.
- Tests: 162 passed. Ruff and Pyright passed with no findings.

## Not promoted

SEC acceptance-time joins, authoritative security-master provenance, live
DeepSeek, and live TradingAgents were not exercised in this checkpoint. They
remain unverified or unavailable and cannot yield executable authorization.
Yahoo remains real-shadow, last-only, and non-execution-grade.

## Safety posture

There is no broker, Schwab, real-account, order, execution, or FinRL-X
production connection. No secret or environment value was read. Any future
shadow daily output must remain `SHADOW / NOT AUTHORIZED FOR ENTRY`.

## Current blockers for a 3B.7 completion claim

- No independently verified SEC acceptance-time evidence has yet been joined
  to a Company Facts observation.
- No authoritative provenance has been collected for the full 11-security
  bounded universe.
- No real certified evidence view has been built from a public provider.

These are explicit certification gaps, not grounds for an authorization bypass.