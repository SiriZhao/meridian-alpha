# Host-to-Skill contract

This is the provider-independent handoff contract for a ChatGPT Host. The
Host may use an authorized account capability, or the user may supply a fresh
sanitized JSON envelope. Conversation memory, browser scraping, broker login,
and provider credentials are never account truth.

## Envelope

Pass one JSON object matching `HostAccountSnapshotEnvelope`:

- `schema_version`: `"1"`
- `snapshot_id`: stable non-secret identifier
- `source_kind`: provider-independent source category
- `source_name`: sanitized source label
- `as_of`: timezone-aware UTC/offset timestamp for the account state
- `retrieved_at`: timezone-aware timestamp when the Host obtained the state
- `coverage_status`: `COMPLETE`, `PARTIAL`, `STALE`, `UNAVAILABLE`, or `CONFLICTING`
- `base_currency`: ISO-4217 code, normally `USD`
- `cash`: non-negative decimal
- `total_equity`: non-negative decimal, at least cash
- `positions`: array of `{canonical_asset_id?, ticker, quantity, market_value?, cost_basis?, currency}`
- `pending_or_unknown_state`: optional sanitized warning, never raw connector text
- `warnings`: sanitized warning strings
- `provenance_digest`: deterministic SHA-256 over the canonical envelope without this field

Position tickers must be canonical uppercase symbols with no duplicate entries.
Do not include account numbers, usernames, access/refresh tokens,
Authorization headers, passwords, secrets, connector payloads, or raw responses.

## Handoff sequence

1. Host validates the JSON shape and recursively rejects sensitive keys.
2. Meridian validates the provenance digest and system-owned freshness against
   the current clock. The input cannot self-assert freshness.
3. Meridian resolves identities through the explicitly certified Security
   Master and normalizes the account.
4. `HOST_NATIVE` executes the deterministic core only when the Python Meridian
   runtime is actually available. Otherwise return
   `MERIDIAN_RUNTIME_UNAVAILABLE` with the missing capability.
5. Return only the sanitized Chinese report, evidence lineage, target portfolio,
   risk/reconciliation status, and explicit blockers. A manual draft requires
   the sealed seven-gate `ManualReadinessCertificate` plus a certified
   `ExecutionQuote`; it is always `NOT_EXECUTED`.

A later Host snapshot—not a recommendation or draft—proves any external fill.