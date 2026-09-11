# Meridian Financial Research V2 — Market Data Plane

Date: 2026-09-11  
Status: **PARTIAL — external public-market retrieval blocked safely**

## Delivered data-plane capabilities

Meridian retains its provider-neutral research contracts: `ResearchDataRequirement`,
`EvidenceRecord`, `ResearchEvidencePackage`, `ProviderResult`, `ProviderFailure`,
`ProviderHealth`, `SourceConflict`, and `DataQualityScore`. Accepted numerical
evidence retains symbol, field, value, unit, source, provider, timestamps,
cutoff, confidence, validation status, and provenance reference. Values without
provenance cannot instantiate an evidence record.

The existing historical chain remains provider-neutral and ordered through the
retrieval orchestrator: local cache, Yahoo historical, Stooq historical, then
other registered structured providers. A provider failure is captured per
requirement and does not abort a subsequent eligible provider. In particular,
Stooq HTTP 404 remains `STOOQ_SYMBOL_NOT_FOUND` rather than a generic failure.

The deterministic feature engine now adds local-only:

- 1D, 5D, 20D, 60D, YTD, and 1Y return
- SMA20/50/200 and EMA20/50
- RSI14 and ATR14
- 20D/60D realized volatility
- ADV20 and relative volume
- current drawdown, max drawdown, 52-week high/low distance, and gap
- aligned SPY beta/correlation and SPY/QQQ 20D/60D relative performance

Benchmark returns are aligned by shared market session dates; independent
provider arrays are never index-zipped. Future bars are excluded before all
calculations. Missing benchmarks yield unknown metrics rather than estimates.

`quant_metrics` was extended rather than duplicated. It accepts optional SPY
and QQQ provenance-bearing rows, returns only deterministic metrics plus a
bounded research view, and omits raw series from its response. `research_packet`
continues to compact raw OHLCV into coverage metadata before it reaches Astra.
No Skill-facing MCP tool invokes another LLM.

## Verification

- Full test suite: **442 passed**
- Ruff: PASS
- Pyright: **0 errors, 0 warnings**
- New V2 coverage verifies deterministic feature output, future-bar exclusion,
  unknown benchmark handling, and bounded MCP output.
- Existing coverage verifies provider success/fallback, both-provider failure,
  cache behavior, conflict handling, Stooq 404 specificity, provenance,
  bounded package views, and no fabricated values.

## Real Astra smoke

Fresh host session `01a09036-949d-7832-a389-90d27f8b1c8e` ran
`gpt-6-astra` at reasoning effort `high` in a read-only sandbox. It discovered
the installed Meridian Skill and called `runtime_status`, `market_snapshot`,
`company_facts`, and `get_provider_health`.

The result was safely `BLOCKED_MARKET_DATA`:

- Yahoo MSFT/SPY/QQQ observations were stale.
- Stooq public fallback returned HTTP 404.
- No usable historical bars were returned, so `quant_metrics` correctly was not
  called and all price/trend/volatility/drawdown/relative values remained
  unknown.
- Official SEC company-fact evidence remained provenance-bearing and separate
  from unavailable market data.
- `execution_authority` remained `NONE`; no broker action was attempted.

This is evidence that failure is explicit and fail-closed. It does not satisfy
the phase's real-data PASS criterion, which requires a complete fresh public
market context.

## Remaining blocker

A successful current public market-data source for the real host is required to
close PASS. The correct next action is to repair or add an approved structured
market-data provider behind the existing provider-neutral historical chain,
then rerun one real Astra market-data smoke. Do not loosen freshness or replace
missing prices with web/LLM estimates.