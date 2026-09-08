# Meridian Skill runtime reference

The live Skill uses the Meridian project launcher and canonical CLI:

- `scripts/run_meridian.ps1 doctor --json` for runtime diagnostics.
- `scripts/run_meridian.ps1 paper run --account Schwab-Paper --json` for the
  normal daily workflow.
- `paper status`, `paper history`, and `paper trades` for read-only inspection.

The project runtime owns policy loading, SQLite paths, live public market
provenance, advisory-research configuration and report locations. Do not use a
fixture, legacy profile argument, a second daily wrapper, or a broker API.
Credentials remain environment-only and must never appear in Skill output.
