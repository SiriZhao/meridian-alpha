# Daily manual workflow

1. Run `./scripts/run_meridian.ps1 doctor`.
2. Run `./scripts/run_meridian.ps1 data-status --json`.
3. Obtain a new sanitized Host snapshot and validate it:
   `./scripts/run_meridian.ps1 snapshot validate <file> --json`.
4. Run `./scripts/run_meridian.ps1 daily --snapshot <file> --market-fixture <fixture> --json`.
5. Review the JSON/Markdown artifact under `RuntimePaths/reports`; any draft is
   manual only. `BROKER SUBMISSION = DISABLED` always applies.

The included examples are deliberately stale fake data and demonstrate safe
rejection. A fresh snapshot plus current normalized observations can produce a
deterministic `DRAFT`, never an executed order. `READY_FOR_MANUAL_ENTRY` still
requires the pre-existing sealed manual-readiness and execution-quote
certificates; operational public prices cannot satisfy that gate.
