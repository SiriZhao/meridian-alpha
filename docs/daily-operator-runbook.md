# Daily operator runbook

1. Obtain a new sanitized `HostAccountSnapshotEnvelope` from an authorized host.
   Do not include account numbers, credentials, tokens, or raw connector payloads.
2. Validate the envelope and freshness with `meridian host-smoke <file>`.
3. Run `meridian daily --account-fixture <sanitized-file> --date <ISO-time>` in
   the intended profile. The default is `TEST`; use `SHADOW_LIVE` only with the
   existing explicit research opt-in.
4. Read the leading report status (`BLOCKED`, `ANALYSIS_ONLY`, `SHADOW`, or
   `READY_FOR_MANUAL_ENTRY`). A shadow result is never an order.
5. Review account truth, certified evidence, quant output, risk, reconciliation,
   provider health, and the target portfolio. Never infer a fill from a target.
6. If a manual-entry candidate is ever shown, independently verify the current
   account and certified execution quote immediately before human entry.

There is no automatic execution profile. A later host snapshot is the only proof
of an external trade, fill, deposit, withdrawal, or corporate action.
