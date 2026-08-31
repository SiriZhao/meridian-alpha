# FinRL-X challenger promotion policy

FinRL-X is an optional, isolated allocator challenger. Meridian passes only a
frozen PIT-safe feature snapshot, a sanitized account state, deterministic
constraints, and a complete artifact manifest. The boundary returns proposed
weights and diagnostics only; it cannot access brokers, orders, credentials,
execution pricing, or account mutation.

## Status semantics

- `DEVELOPMENT_MODEL`: bounded experiment; never a production challenger.
- `ARTIFACT_VALIDATED`: bytes/provenance are checked, but OOS evidence is not
  established.
- `OOS_VALIDATED_SHADOW`: all manifest fields, chronological walk-forward
  windows, PIT checks, and transaction-cost-aware OOS evidence are present.
- `PROMOTION_ELIGIBLE`: a future human decision state, not an automatic action.

The legacy `VALIDATED_SHADOW` value is retained only for old fixtures and does
not imply OOS validation. Placeholder strings such as `unavailable` and
`not_run` cannot satisfy the OOS gate. Artifact bytes are re-hashed immediately
before inference; mismatch is `MODEL_INVALID` for a genuine OOS challenger.

## Future human gate

Promotion requires a fully certified artifact, deterministic replay, no
look-ahead/PIT failures, sufficient multi-window OOS evidence, acceptable
risk/concentration/turnover, transaction-cost-aware results, and a
statistically/economically defensible improvement. A human must approve a
separate gate. This checkpoint performs no training, inference, or promotion.
