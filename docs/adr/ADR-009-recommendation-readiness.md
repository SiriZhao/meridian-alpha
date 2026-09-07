# ADR-009 — recommendation diagnostics and snapshot receipts

Accepted for Controlled Improvement Phase 1; production acceptance remains blocked.

Reuse ReadinessStatus/host_readiness for RecommendationReadiness. Compute
research, recommendation and manual outcomes separately. No missing dimension
can imply success. Public quotes cannot grant execution certification; sealed
manual authority remains mandatory and is not replaced by this aggregate.

Persist immutable diagnostics and hashed snapshot receipts in AuditStore SQLite
v2. Claim each fresh explicit snapshot once across processes; keep claims after
failure. Hashes establish consistency, not authentication. A verifiable Host
source and certified research are future acceptance inputs, not inferred facts.

Live retrieval may close its cutoff after reception only through explicit live
mode. Default fixed/replay cutoff never advances. No broker capability, risk,
pricing, allocator or model-provider boundary changes are authorized here.
