# Real Host smoke checklist

Run only with an explicitly authorized sanitized Host envelope. A fixture is
useful for tests but cannot claim real Host smoke.

- [ ] Fresh timezone-aware `as_of` and `retrieved_at`; neither is future and
      system time owns freshness.
- [ ] `snapshot_id` is stable; duplicate content is idempotent and a conflicting
      digest is rejected.
- [ ] Currency is explicit and supported; cash/equity/position values are
      non-negative and internally coherent.
- [ ] Coverage is `COMPLETE` for any manual-readiness attempt; partial/stale/
      unavailable/conflicting input fails closed.
- [ ] Positions resolve through the authoritative certified Security Master.
- [ ] Provenance digest matches canonical sanitized content.
- [ ] Recursive sensitive-key scan passes; no account IDs, credentials, tokens,
      raw connector payloads, or raw responses are present.
- [ ] Account, security, market, research, quote, risk, and reconciliation
      gates are evaluated; all seven must pass for manual readiness.
- [ ] Output is sanitized and records only hashes/IDs, gate statuses, and
      blockers. Never persist raw account input or infer a fill.

Successful completion may be labeled `REAL_HOST_DATA_SMOKE_COMPLETE` only after
these checks pass against externally authorized input.