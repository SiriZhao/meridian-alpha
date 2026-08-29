# Host account contract

The Host supplies a provider-independent `HostAccountSnapshotEnvelope`: a
snapshot ID, source label, as-of/retrieved timestamps, coverage status, base
currency, cash, equity, and position facts. Position facts contain a canonical
asset/ticker, quantity, supplied market value, optional supplied cost basis,
and currency.

Never supply or persist account numbers, usernames, access tokens, credentials,
or raw connector responses. Meridian records only sanitized decision artifacts
and hashes. `COMPLETE` is required for eventual manual-entry readiness;
`PARTIAL` is analysis-only; `STALE`, `UNAVAILABLE`, and `CONFLICTING` block.
A recommendation is never evidence of a fill.