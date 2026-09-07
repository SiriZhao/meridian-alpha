# Daily operator runbook

Follow the canonical Windows command in [README](../README.md).

1. Run doctor; correct FAIL diagnostics. Daily initializes a missing DB.
2. Supply a new sanitized HostAccountSnapshotEnvelope; never assume prior fills.
3. Run daily --snapshot <absolute-file> --json.
4. Read output_files and separate runtime completion from recommendation readiness.
5. Current canonical output is research-only. Read the actual research status. A DRAFT
   does not have sealed seven-gate manual authority or a certified quote.

No broker execution or automatic orders. Missing fresh account/market facts
cannot be inferred from conversation or fabricated. Use fixture input only for
explicit regression, never for a real account request.


Read `readiness` first. Runtime PASS only says the invocation completed its
operational work. Recommendation remains BLOCKED if any required dimension is
UNKNOWN, NOT_RUN, stale, unverified or incomplete. Public quotes never certify
manual execution. AVAILABLE research means validated model inference, not certification.

Use `snapshot validate <file> --json` to inspect freshness and hashed identity
without consuming input. Daily records each snapshot once across processes;
REPLAYED or ID_CONFLICT requires a new Host snapshot. Never change an ID simply
to disguise a replay. Pending/partial state blocks the decision path.

For provider failures, inspect both lanes in `provider_probes`: attempt/completion
and receipt times, observed session, cutoff, selection, cache, and final status.
During closure, LAST_COMPLETED_SESSION_ONLY is context, not a freshness override.


## Optional canonical research

Use the existing `models.yaml` research settings in the selected policy directory
(`MERIDIAN_POLICY_DIR` if configured): `live_enabled: true`, provider `deepseek`,
and the configured model. Supply the credential through the environment reference
`DEEPSEEK_API_KEY`; never include its value in commands, reports or chat.
No default policy or model was changed by Batch 2.

The same daily command invokes the stage only after input validation. The actual
request is the provider probe. Inspect `research.context.status`, `attempts`,
`provenance`, `error_code`, and `next_action`. AUTH_FAILED requires correcting the
credential externally; TIMEOUT/RATE_LIMITED/UNAVAILABLE remain blocked after bounded
retry. INVALID_RESPONSE is never converted into a neutral or prior-day signal.
A missing snapshot prevents the stage entirely. No automatic cached research is used.
Public advisory success is AVAILABLE, while certified research/manual gates remain
unmet. See [Batch 2 architecture](adr/ADR-010-canonical-advisory-research.md).


## Failure recovery and acceptance

From any working directory, invoke the launcher by its absolute path:

```powershell
& "E:\CSDIY\Vibe Coding Project\meridian-alpha\scripts\run_meridian.ps1" doctor --json
& "E:\CSDIY\Vibe Coding Project\meridian-alpha\scripts\run_meridian.ps1" daily --snapshot "C:\Inputs\today.json" --json
```

`--snapshot`, `--market-fixture` (regression only), and `--json` are current parser
options; no `--profile` option exists. A process exit of 0 can still carry BLOCKED
recommendation readiness. Read the JSON before presenting a result.

If the checkout virtual environment is missing, the launcher returns
MERIDIAN_PYTHON_MISSING with exit 3 (structured for --json). Restore Python 3.12
and dependencies with `uv sync --inexact --group dev`; do not use system Python
3.14 or exact synchronization as a substitute. Doctor rechecks the restored path.

MERIDIAN_REPORT_WRITE_FAILED retains the analysis run_id and appends a linked
failure receipt where the DB remains writable. `partial_output_files` are incomplete
artifacts, not completed reports; `output_files` only lists usable diagnostic logs.
Do not trust a partial JSON reporting the earlier analysis outcome as successful
report persistence. Inspect free space, permissions and file locks, preserve audit
history, and supply a new snapshot for a subsequent daily run.

[Phase 1 acceptance](controlled-improvement-phase1-acceptance.md) distinguishes
verified regression behavior from blocked real Host/research acceptance.
