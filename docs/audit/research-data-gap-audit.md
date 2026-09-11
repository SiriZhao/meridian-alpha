# Meridian research data-gap audit

Date: 2026-09-11  
Scope: canonical daily and Schwab-Paper research path only

## Executive finding

The initial failure was not a Codex structured-output defect: the canonical caller gave Codex only a bounded list of current public observations. The migrated path now inserts a bounded gap-planning and retrieval loop before final research. Numerical evidence is fetched through provider chains and deterministic features are calculated locally; qualitative web research is isolated to sourced event/news findings. When the local Codex account is quota-limited, the planner fails closed as `CODEX_RATE_LIMITED` and no provider fallback is attempted.

The least invasive insertion point is immediately before the final provider invocation inside `CanonicalResearchStage`. A retrieval preparation service can enrich a provider-neutral evidence package without changing the downstream `ResearchDecisionContext`, allocation, order sizing, execution quote, reconciliation, or human approval contracts.

## Current call chain

1. `MeridianApplicationService._daily` validates the account snapshot and builds an operational market snapshot.
2. `OperationalMarketSnapshotService.from_runtime` installs Yahoo Chart as the primary quote provider, Stooq as the secondary quote provider, a provenance-preserving operational cache, and Yahoo Chart as the only historical OHLCV provider.
3. `_daily` converts accepted `MarketSnapshot` objects into `PublicResearchObservation` values and builds `DailyResearchInput`.
4. `CanonicalResearchStage.run` enforces freshness, provider configuration, cutoff, replay, fixture, and research-budget gates.
5. `CodexCliProvider.run` converts the request to `ResearchPacket`, invokes local `codex exec` in a read-only sandbox, and validates the schema and evidence references.
6. `ResearchPreparationService` asks the local Codex gap planner for missing requirements, retrieves evidence for at most three rounds, validates provenance/quality/conflicts, and passes only a bounded `research_view()` to final research. Raw OHLCV remains local to deterministic analytics/audit and is not sent as a giant series.
7. If Codex returns `INSUFFICIENT_DATA` or the planner/retrieval path fails, `CanonicalResearchStage` emits no `DailyResearchOutput` and therefore no research authorization.
8. `DailyClosureService` preserves the research failure as a deterministic blocked reason. `paper_run` converts the result to `PAPER_BLOCKED`; no automatic execution path exists.

Legacy generic states (`INVALID_RESPONSE`, `RESEARCH_INVALID_RESPONSE`) remain in compatibility enums/tests and older report paths. The Codex production path now emits actionable `CODEX_*` errors. They are historical compatibility surface, not the cause of the current data-gap result.

## Data already present

| Area | Current implementation | Present in final Codex packet? | Limits |
|---|---|---:|---|
| Account snapshot | host/paper snapshot validation in `application.py` | In-memory cash/equity/weights/positions summary only | Excluded from request dumps, hashes, reports, replay artifacts, and retrieval audit |
| Current public price | Yahoo Chart primary; Stooq fallback; fresh operational cache | Yes | Public research observation only; never execution-grade |
| Daily return / gap / ATR | `OperationalMarketSnapshotService` builds daily return, gap and ATR14 | Only daily return | ATR/gap lineage is discarded before Codex packet construction |
| Historical OHLCV | `YahooChartHistoricalProvider` and `HistoricalBarSeries` | No | Single live source in canonical path; unverified PIT status |
| Existing technical features | `market.feature_set` has SMA20/50, RSI14, ATR14, realized volatility, volume ratio, gap, and VWAP proxy | No | Missing 5/20/60-day, YTD, SMA200, EMA, drawdown, 52-week distances, beta/correlation |
| Fundamentals | SEC Company Facts observations, accession certification, snapshots, and evidence conversion | No | CIK map currently covers a small hard-coded universe; canonical daily does not invoke it |
| Company events | SEC filing metadata/event models | No | Filing-presence lane, not general news content |
| News and macro | project-owned protocols and replay/test providers exist | No | No canonical live news or macro provider is connected |
| Evidence system | `EvidenceItem`, `ResearchEvidencePacket`, builders, completeness evaluation, PIT states | No | Designed for certified research paths; canonical Codex daily bypasses it |
| Cache | operational quote cache plus research packet stores elsewhere | Partial | No general requirement-aware TTL cache for historical/fundamental/news evidence |
| Strategy policy | risk/allocation/model YAML policies | Hash only | Investment horizon and decision frequency are not explicit facts in the packet |

## Common missing fields

The canonical packet routinely lacks historical OHLCV, multi-horizon returns, long trend (SMA200), volume history/ADV20/relative volume, realized volatility, drawdown, relative benchmark performance, fundamental/valuation context, earnings/event context, macro/rates/volatility context, existing-position context, and explicit investment horizon. News and analyst consensus are optional for a numerical decision; current market snapshot, historical prices, portfolio context, and strategy policy are blocking requirements.

## Provider failures and exact Stooq 404 path

The runtime quote path is:

`application._daily` → `OperationalMarketSnapshotService.from_runtime` → `OperationalRefreshService.refresh` → primary `YahooChartQuoteProvider.get_quote` and secondary `StooqQuoteProvider.get_quote` → `urllib.request.urlopen`.

Stooq constructs `https://stooq.com/q/l/?s=<provider-symbol>&f=sd2t2ohlcv&h&e=csv`. An HTTP 404 raises `HTTPError`, caught by the provider's broad `OSError` handler and re-raised as `QuoteProviderError`. `OperationalRefreshService._fetch` inspects the cause and records `http_404`. Because both quote lanes are attempted before selection, a Stooq 404 does not override a successful Yahoo quote. If both fail, `_missing_code` currently collapses the final symbol outcome to `PRIMARY_PROVIDER_UNAVAILABLE_AND_SECONDARY_PROVIDER_UNAVAILABLE`; it does not expose the more useful `STOOQ_SYMBOL_NOT_FOUND` state.

The historical path is different: `OperationalMarketSnapshotService._market_snapshot` invokes only `YahooChartHistoricalProvider`. A historical Yahoo timeout/malformed response has no historical fallback and causes that symbol to be missing. Stooq is not currently a historical provider.

## Why Codex cannot fill the gaps today

- `ResearchPacket.from_daily_input` serializes only `DailyResearchInput.observations` into both signals and regime inputs.
- Factor, risk, performance, positions, and proposed-change dictionaries remain empty.
- The stable research prompt explicitly disables external research and directs Codex to use only the supplied packet.
- `codex exec` is launched without `--search` and with `--ignore-user-config`, so no live Web browsing is available.
- `DailyResearchOutput.validate_input` only permits citations to the original observation hashes. A newly discovered source would be rejected even if Codex mentioned it.
- There is no typed data-requirement plan, retrieval registry, evidence merge, quality score, or bounded second research pass in the canonical stage.

This is correct fail-closed behavior but incomplete preparation.

## Components to retain

- `DailyResearchInput`, `ResearchDecisionContext`, `ResearchStageResult`, and downstream decision consumption.
- Local `CodexCliProvider`, ChatGPT-managed authentication, sanitized child environment, schema output, timeout, and bounded repair retry.
- Existing operational quote/cache/freshness implementation and strict separation from execution quotes.
- `HistoricalBarSeries`, SEC fundamental certification, company event models, security master, evidence/PIT primitives, deterministic closure/risk/order/manual gates.

## Components to add or extend

- A provider-neutral `ResearchDataRequirement` schema and provenance-bearing `ResearchEvidencePackage`.
- A structured Codex data-gap planner that requests fields but is forbidden to return market values.
- A bounded retrieval orchestrator with cache, provider registry, fallback diagnostics, conflict validation, and health/circuit state.
- A historical provider chain. Yahoo remains the current primary implementation; injected/local/cache providers make fallback generic. Stooq 404 receives a specific failure code and never aborts the chain.
- Deterministic derived-feature computation from accepted OHLCV.
- Explicit strategy profile/policy context including investment horizon.
- Optional qualitative Codex Web Research with `--search`, citations, and no numerical-authority path.
- A maximum-three-round preparation loop followed by one final canonical research call.
- `ResearchEvidencePackage.research_view()` to bound final prompt size while retaining evidence IDs and provenance.
- In-memory-only portfolio context derived from the current `AccountSnapshot`; account identifiers are never sent or persisted.
- Optional second-source collection for critical numerical requirements with scalar, snapshot-price, and latest-session OHLCV conflict checks.
- Redacted audit artifacts that record public requirements/evidence and hashes, never raw account snapshots or credentials.

## Safety boundary

Retrieval evidence is research evidence only. Public Yahoo/Stooq/Web values cannot become execution quotes, cannot clear stale/closed-market gates, and cannot determine quantities or limit prices. A missing fresh executable price, missing provenance, blocking numerical gap, critical source conflict, stale account state, or closed market remains execution-blocking even if qualitative research completes.


