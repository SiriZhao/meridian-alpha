---
name: meridian-alpha
description: Run Meridian daily portfolio decision support through its installed canonical CLI, diagnose runtime failures, and present sanitized research-only results without broker execution.
---

# Meridian daily operation

Use the installed `meridian` command (equivalently `python -m meridian`). On
this Windows checkout the stable launcher is `scripts/run_meridian.ps1`.
Do not call legacy internal CLI modules or the old scripts in this Skill.

1. Run `meridian doctor --json`. If the only degraded check is a missing DB,
   daily initializes it safely. For FAIL, resolve the reported runtime issue.
2. Obtain a newly supplied sanitized `HostAccountSnapshotEnvelope`; see
   [account-contract.md](references/account-contract.md). Never infer current
   cash, holdings or fills from conversation history or earlier recommendations.
3. Run `meridian daily --snapshot <absolute-sanitized-envelope.json> --json`.
   It performs initialization/preflight, public market retrieval, deterministic
   analysis, audit persistence and report generation. No real snapshot: request
   one; never substitute a synthetic account for a real daily request.
4. Read the JSON result and its `output_files`. Present runtime/data/portfolio/
   research/quant/risk/recommendation status, warnings, errors and report paths.
   Read the typed `readiness` object, `snapshot_provenance`, and `provider_probes`.
   Runtime PASS does not imply recommendation PASS. UNKNOWN, NOT_RUN, stale,
   incomplete, replayed, synthetic, and unauthenticated inputs cannot authorize
   recommendation. `quote_certification_status` remains BLOCKED for public data.
   Missing/replayed snapshots produce diagnostic reports without running analysis.
   Validate-only does not consume a snapshot; daily atomically records its hash.
   A blocked investment recommendation is distinct from a runtime failure.

For regression only, add `--market-fixture <absolute-synthetic-market.json>`
with a synthetic account. Label results FIXTURE; never claim live verification.
Read `research`, `decision_context`, `gates`, and `stages` in the daily JSON.
Enabled research uses validated public inputs; AVAILABLE requires a validated
response, and FIXTURE is never a live probe. Disabled research is NOT_RUN.
Advisory output cannot confer certified research or manual-entry authority. Old `--profile`, `--date`, and `--account-fixture`
arguments are not supported by this CLI.

All current outputs are research-only and NOT_AUTHORIZED_FOR_MANUAL_ENTRY.
DRAFT is not a sealed ManualReadinessCertificate. A manual-entry candidate
requires all seven authority gates and a matching certified ExecutionQuote;
never derive that authority from a successful process exit or report status.
No broker login, write, execution, or assumed fills. Do not read or print
credentials or raw account identifiers. See [safety.md](references/safety.md).

If the installed Python/package is missing, report MERIDIAN_RUNTIME_UNAVAILABLE
with the missing capability. Do not reproduce financial calculations in prose.
