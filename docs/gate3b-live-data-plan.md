# Gate 3B supervised live-data plan

This is a plan only. No provider is selected or connected in Night Phase Part 2.
Unknown capabilities are marked TO VERIFY.

| Area | Required fields | Point-in-time requirement | Freshness | API key | Executable-path critical | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| Execution quote provider | ticker, timestamp, last, bid, ask, previous close, volume, provider | Timestamp must be at or before run time; quote semantics TO VERIFY | Enforce quote_max_age_seconds and spread/gap gates | TO VERIFY | Yes | Block executable output; never substitute a stale mark |
| Historical OHLCV | ticker, bar timestamps, OHLC, volume, adjustment metadata | No bar after as_of; corporate-action treatment TO VERIFY | Cache key includes ticker/interval/start/end/provider | TO VERIFY | Yes for backtests | Fail closed or use a clearly marked replay fixture |
| SEC/EDGAR fundamentals | accession/document ID, filing timestamps, period, facts, source URI | available_at must be no later than as_of; filing availability TO VERIFY | Filing-age policy by fact type | Usually no, TO VERIFY | Research-grade, not direct order authority | Mark research incomplete |
| News evidence | article/document ID, source, published/observed/available timestamps, URI, summary | available_at <= as_of; retrospective edits TO VERIFY | Per-type maximum age | TO VERIFY | Research grounding critical | Mark INSUFFICIENT_GROUNDING |
| Security metadata | ticker, asset_type, sector, industry, effective timestamps | Classification effective at as_of | Security-master freshness TO VERIFY | TO VERIFY | Yes when sector caps apply | Block executable output for unknown required metadata |
| Macro data | series ID, observation/release timestamps, value, source | Release/available timestamp <= as_of | Series-specific freshness | TO VERIFY | Regime/research dependent | Omit macro input and mark degraded research |

Every live adapter must expose capability metadata, preserve provider
provenance, and remain separate from brokerage execution. Gate 3B must include
supervised replay comparisons, failure injection, no-look-ahead tests, and a
credential review before any executable-path enablement.

## Gate 2.6 boundary note

This plan is future work only. No live market, SEC, news, macro, metadata, or
execution provider is selected or connected in Gate 2.6.
