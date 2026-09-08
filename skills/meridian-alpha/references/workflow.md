# Meridian workflow reference

For normal operation, the authoritative paper workflow is:

`Schwab-Paper ledger → fresh PAPER_LEDGER envelope → canonical daily → live public market → advisory research → deterministic decision and gates → eligible paper fill → ledger and reports`

Use `scripts/run_meridian.ps1 paper run --account Schwab-Paper --json` from the
Meridian project root. The account initializes to USD 100,000.00 only once and
subsequent runs use its persistent ledger. Fixture data, inferred holdings and
parallel daily wrappers are prohibited.

A real-Host workflow is separate and only applies when the user explicitly
supplies a new authorized sanitized HostAccountSnapshotEnvelope. It must not be
presented as the Schwab-Paper account.
