# Host integration runbook v2

The host supplies only the sanitized `HostAccountSnapshotEnvelope` contract.
Required safe provenance is `source_name`, `snapshot_id`, `as_of`,
`retrieved_at`, coverage, currency, positions, cash, warnings, and a provenance
digest. Sensitive connector fields are rejected and never logged.

The pipeline validates freshness, resolves symbols through the verified Security
Master, normalizes holdings/cash, and runs the same daily analysis path used by
replay and shadow. Partial, stale, future, duplicate, or identity-mismatched
snapshots fail closed. The host remains the account source of truth; Meridian
does not authenticate to an account source or mutate account state.
## V1 frozen workflow

Supply only a sanitized `HostAccountSnapshotEnvelope` through the host boundary,
then run `meridian host-smoke <file>` followed by `meridian daily --account-fixture <file>`.
The host owns current time and account truth; Meridian rejects future/stale,
sensitive, duplicate-conflicting, or unverifiable snapshots. No browser cache,
credential store, broker API, or raw connector payload is inspected.
