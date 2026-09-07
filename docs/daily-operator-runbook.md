# Daily operator runbook

Follow the canonical Windows command in [README](../README.md).

1. Run doctor; correct FAIL diagnostics. Daily initializes a missing DB.
2. Supply a new sanitized HostAccountSnapshotEnvelope; never assume prior fills.
3. Run daily --snapshot <absolute-file> --json.
4. Read output_files and separate runtime completion from recommendation readiness.
5. Current canonical output is research-only. LLM research is NOT_RUN. A DRAFT
   does not have sealed seven-gate manual authority or a certified quote.

No broker execution or automatic orders. Missing fresh account/market facts
cannot be inferred from conversation or fabricated. Use fixture input only for
explicit regression, never for a real account request.


Read `readiness` first. Runtime PASS only says the invocation completed its
operational work. Recommendation remains BLOCKED if any required dimension is
UNKNOWN, NOT_RUN, stale, unverified or incomplete. Public quotes never certify
manual execution. The current canonical research adapter has not run.

Use `snapshot validate <file> --json` to inspect freshness and hashed identity
without consuming input. Daily records each snapshot once across processes;
REPLAYED or ID_CONFLICT requires a new Host snapshot. Never change an ID simply
to disguise a replay. Pending/partial state blocks the decision path.

For provider failures, inspect both lanes in `provider_probes`: attempt/completion
and receipt times, observed session, cutoff, selection, cache, and final status.
During closure, LAST_COMPLETED_SESSION_ONLY is context, not a freshness override.
