# TradingAgents v0.5.x review

Review date: 2026-09-29. v0.5.1 was verified from the public GitHub Releases
API: tag `v0.5.1`, published `2026-09-24T07:51:56Z`, release commit resolved
through the public tag. The repository also contains a read-only v0.5.0 audit at
`docs/upstream/tradingagents-v0.5.0-gap-audit.md`.

| Area | Upstream behavior | Meridian decision | Implementation / risk |
|---|---|---|---|
| Point in time and as-filed SEC | Date injected into tools; filings selected by availability/acceptance | **ADOPT** | `ResearchTemporalContext`, evidence availability checks, SEC filing tests. |
| Portfolio context | Optional portfolio state distinct from a flat book | **ADAPT** | Sanitized `portfolio_context`; missing state remains unknown and cannot size orders. |
| Decision parsing | Unreadable/conflicting rating can be REVIEW | **ADOPT** | `REVIEW_REQUIRED` and execution gate regression tests. |
| Vendor failures | Errors/sentinels distinguish unavailable feeds from no event | **ADAPT** | Provider health and explicit degraded statuses; no negative inference. |
| Run isolation | Backtest cells and graph state are scoped per run | **ADOPT** | `run_id` temporal context and isolated replay logs; no singleton research state. |
| Backtest grid | Ticker/date cells with delayed outcome settlement | **ADAPT** | `ResearchBacktestRunner`, PIT context, calibration summary. |
| Checkpoint identity | Resume/checkpoint metadata protects configuration identity | **ADAPT** | Replay resume is scoped to run and date; canonical ledger is never a checkpoint store. |
| Model routing | Deep/quick roles and bounded retries | **ADAPT** | Role model policies plus bounded native budget and monotonic deadline hierarchy. |
| Structured output / price grounding | Schema validation and reported-price context | **ADOPT** | Evidence IDs are validated; executable prices require verified market snapshots. |
| Test isolation | Hermetic tests and explicit retry bounds | **ADOPT** | Injected clocks/runners and bounded retry tests. |
| v0.5.1 package/vendor reorganization | Modules moved under purpose-specific packages | **NOT_APPLICABLE** | Meridian has project-owned providers and does not copy import layout. |
| v0.5.1 SEC CAPEX aliases | Purchases of productive assets cover NVIDIA/Amazon taxonomy variants | **ADAPT** | Meridian currently maps only `PaymentsToAcquirePropertyPlantAndEquipment`; equivalent aliases remain a documented capability gap and must not be treated as zero CAPEX. |
| v0.5.1 historical date leakage | Future/today date removed from historical context | **ALREADY_COVERED** | Temporal cutoff checks and replay tests reject post-cutoff facts; date injection audit remains required. |
| v0.5.1 blank result paths | Blank environment value preserves default | **ALREADY_COVERED** | `RuntimePaths.from_environment` treats empty overrides as absent. |
| v0.5.1 HTML social normalization | StockTwits text is plain text, not escaped HTML | **NOT_APPLICABLE** | Meridian has no active StockTwits HTML ingestion path. |
| v0.5.1 independent vendor state | Separate graphs do not share vendor state | **ALREADY_COVERED** | Meridian provider calls and run contexts are scoped per run; no vendor singleton is used. |
| v0.5.1 checkpoint status | Resume vs fresh start is explicit | **ADAPT** | Replay logs are run/date scoped; canonical paper ledger is not a checkpoint store. |
| v0.5.1 Jev screening | Optional TypeSafe social-post screening | **REJECT** | No social-post source is active in Meridian; adding a vendor would not improve current gates. |
| v0.5.1 GPT-6 defaults | Sol/Luna selected upstream | **REJECT** | Meridian keeps capability-aware configured `gpt-5.6-luna`/low route. |
| LangGraph/vendor runtime | Full upstream graph and provider SDK | **REJECT** | Would blur Meridian's Research → Decision → Execution boundary and add authority. |
| Broker execution / portfolio manager sizing | Upstream patterns are not execution authority here | **REJECT** | PAPER remains broker-disabled; deterministic Meridian risk/allocation owns orders. |

## Stability conclusion

Meridian adopts research-integrity ideas as project-owned contracts. Upstream
models, vendors, memory, and graph runtime are not dependencies. The current
runtime evidence remains fail-closed: provider failures produce degraded or
blocked research, never a fabricated successful report.
