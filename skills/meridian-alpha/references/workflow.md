# Meridian workflow reference

For normal operation, the authoritative paper workflow is:

`Schwab-Paper ledger → fresh PAPER_LEDGER envelope → canonical daily → live public market → advisory research → deterministic decision and gates → eligible paper fill → ledger and reports`

Use `scripts/run_meridian.ps1 paper run --account Schwab-Paper --json` from the
Meridian project root. The account initializes to USD 100,000.00 only once and
subsequent runs use its persistent ledger. Fixture data, inferred holdings and
parallel daily wrappers are prohibited.

In Codex, this is a canonical-runtime write workflow. Request approved host
execution before running either `doctor --json` or the paper command. The
launcher selects the repository environment but cannot promote a restricted
sandbox process into the host context. MCP is not a host-execution bridge.

Run host-approved `doctor --json` first and continue only on `PASS`; then run
the paper command through the same approved host boundary. If approval has not
been granted, return `HOST_APPROVAL_REQUIRED`. If approved host execution is
unavailable or rejected, return `HOST_EXECUTION_UNAVAILABLE`. Do not try the
command in the restricted sandbox and do not report a database/storage failure
when no host command ran.

A real-Host workflow is separate and only applies when the user explicitly
supplies a new authorized sanitized HostAccountSnapshotEnvelope. It must not be
presented as the Schwab-Paper account.
