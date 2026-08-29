# Corporate Action Contract

`meridian.corporate_actions.CorporateActionEvent` models split, cash dividend,
stock dividend, symbol change, delisting, merger and acquisition events using
Meridian-owned fields. It distinguishes event/effective dates from
`announcement_at` (known-at evidence), `first_seen_at`, value/ratio/currency,
provider and provenance.

## Certification

`CERTIFIED_HISTORICAL_PIT` requires an announcement timestamp and an
announcement no later than the decision cutoff. If known-at evidence is
missing, the event remains
`NOT_CERTIFIED_FOR_HISTORICAL_INFORMATION_EVENT` or `UNKNOWN`; an old event
date alone is not enough.

`LIVE_FORWARD_FIRST_SEEN` records what Meridian legitimately observed in the
forward stream. It is not backdated evidence for a historical decision.

## First-seen ledger

`FirstSeenLedger` is append-only, keyed by stable event ID, provider and
payload hash. A row's `first_seen_at` is assigned from the ledger clock and
cannot be replaced by an older event timestamp. Optional persistence is a
sanitized JSON ledger; it contains no credentials, account data or hidden
reasoning.

Provider disagreements produce `MARKET_DATA_CONFLICT` diagnostics. Meridian
does not silently choose or average conflicting corporate-action facts.

