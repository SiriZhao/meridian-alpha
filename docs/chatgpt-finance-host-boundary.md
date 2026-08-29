# ChatGPT Finance Host boundary

## Host supplies

A sanitized, current `HostAccountSnapshotEnvelope`. The envelope deliberately
has no account number, username, token, credential, or raw connector payload.

## Meridian validates

Schema/timestamps, duplicate tickers, Security Master identity, currency,
coverage, freshness, duplicate snapshot-ID content, and the conversion to the
existing `AccountSnapshot` contract.

## Meridian never receives or does

It never receives secrets or account identifiers; it does not depend on a
ChatGPT Finance implementation, connect to a broker, execute an order, or
infer a fill from a recommendation.

`READY_FOR_MANUAL_ENTRY` requires all deterministic readiness gates, including
an execution-grade quote. Gate 4 currently remains analysis-only when that
quote authority is unavailable.