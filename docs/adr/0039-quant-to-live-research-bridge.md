# ADR 0039 — Quant-to-live research bridge

Status: Accepted for research implementation; no production promotion.

The bridge wraps Mission 1's existing V2.2 numerical engines. Their mathematics,
policies, engine hash and archived experiments remain unchanged. Every revision
binds an aware cutoff, quote observation/availability times, quote and historical
hashes, packet, QuantShadowRecord and policy/engine identities. Evidence is sealed
before GPT. A subsequent quote refresh creates a new fully computed revision,
never a backfill. GPT receives independent serialized copies and cannot modify
scores, ranks or targets. Output schema and quote/quant citations are checked.

Strict history uses existing qualified contracts. Public RAW bars with unknown
corporate actions provide only completed-session open/close, range and observed
dollar-volume diagnostics. No cross-session returns, inferred adjustments,
complete score, OOS qualification or allocation is manufactured. Unverified
adjusted prices remain blocked. A nullable public daily return supports price-only
research; absence is not zero. Existing supplied-return requests are unchanged.

The old daily-return allocator is a clearly identified V1 live reference,
not the canonical daily decision or V2 target. Canonical risk, orders and paper
behavior remain unchanged. SQLite mode=ro/query_only reads validate schema without
migrations or account setup. Ledger versions are checked at read/publication.
Missing state blocks. No broker pending/fill state is inferred or raw user account
snapshot persisted. Canonical Doctor/report/lock probes require approved host.
Readiness never runs daily or paper execution.

Conditional half-ATR/SMA zones require qualified history and a fresh observed
price, with explicit compatible-basis/no-new-action assumptions. They are neither
intrinsic value nor an approved limit. Without evidence, prices/categories wait.
Model opinion/confidence is uncalibrated inference, never probability of profit.

Rollback: retain V1 and parent checkout, omit the optional bridge. No reset,
migration, ledger switch or main merge is necessary.
