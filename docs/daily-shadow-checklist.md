# Daily shadow checklist

Use the single supported `meridian daily` path. The default is safe TEST;
`SHADOW_LIVE` requires explicit opt-in and no profile enables auto execution.

1. Obtain a fresh authorized Host snapshot, or record that no real Host input
   is available. Never use conversation history or an old snapshot as truth.
2. Run `meridian quote-preflight` and record explicit provider health without
   printing credentials.
3. Run the bounded daily analysis, for example:
   `meridian daily --profile SHADOW_LIVE --account-fixture <sanitized-json>`.
4. After the US session has completed, repeat with
   `--session-completed` only when the session really completed.
5. Inspect system health, evidence lineage, and the deterministic target.
6. Confirm the run records code commit, Skill version/hash, policy hashes,
   decision timestamp, provider failures, and shadow-session summary.
7. Confirm append-only ledgers succeeded. A session counts only when every
   qualification gate is true; incomplete sessions do not count.
8. Treat recommendations and targets as observations, never as trades. Apply
   `NEXT_SESSION_OPEN`/the configured assumption only in the separate shadow
   performance ledger.
9. Join 1D/5D/20D outcomes later, only after they become available; never leak
   future data into the decision record.

End-of-run operator fields are Run ID, Version, Status, System health, Account,
Research, Quant, LLM, Target, Quote, Manual readiness, Shadow session count,
and exact blockers. Current V1 acceptance is five completed sessions minimum,
ten preferred; this is operational validation, not performance validation.