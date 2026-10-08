# Mission 2 recovery and function-level gaps

Recovered exact local/remote Mission 1 HEAD: 69eb57aa0f8464b18c98c9464b1c1d52a267c960.
Root: clean Forward Evidence fd7481d. Quant worktree: clean before changes.
New isolated child branch: codex/quant-live-bridge. No main merge or lost changes.
Actual Python/import/policies resolve inside .worktrees/quant-engine-v2; Python
3.12.10. Runtime: E:\MeridianAlphaRuntime, DB db/meridian.sqlite3, cache home/cache.
Research: codex_cli / gpt-5.6-luna / low. Entry: run_live_advisory.ps1.
Canonical policy: quant-v2.1 / QUANT_V1_BASELINE. Challenger: quant-v2.2 SHADOW_ONLY.

| Function / file | Verified gap | Implemented boundary |
|---|---|---|
| LiveAdvisoryService._run | Positive daily_return + confidence=1 allocator could be mistaken for V2 | Explicit V1 live-reference provenance; separate V2.2 packet and typed comparison |
| collect_live_features / completed_session_features | Raw unqualified histories fed cross-session technical returns | Preserve bars/time/source; only within-session public diagnostics with action gap |
| MarketDataFreshnessGate / market_row | available_at not checked; stale last could appear current | Availability checks and separate current versus dated reference |
| fetch_current_quotes | Yahoo-only route failed despite public Nasdaq availability | One primary + one fallback with fresh timestamps, no invented previous close |
| PublicResearchObservation / native _evidence | Mandatory daily return and no Quant catalog | Nullable unknown return; hash/cutoff-bound factor attribution evidence IDs |
| Final GPT advisory | New market refresh detached from earlier signals; no Quant fields | New recomputed/sealed revision and explicitly retained earlier revision |
| render_report | English operational summary without structured Quant provenance | Chinese per-symbol gap/attribution/category/price/scenario/monitoring sections |
| PaperLedger.state/status/export_snapshot | Read APIs internally called migrate | Read-only store validates version and forbids all writes; ledger version recheck |
| run_live_advisory.ps1 | Could use older checkout/interpreter/policies silently | Import-origin assertion, printed policy path, same launcher readiness mode |
| application_cli | No readiness report workflow | live-readiness writes unique immutable real observations without daily execution |
| daily-operator-runbook | Claimed automatic 100000 initialization | Existing account required, preserve history, no reset/init demo |

Unmodified algorithm/safety core: daily_closure, quant engine, orders, risk,
reconciliation, projected portfolio validator, operational snapshot certification,
canonical application daily ownership and paper execution. MCP is not a host
approval bridge; previously running root-based MCP does not acquire these changes.

Pre-change targeted baseline: 87 passed in 24.67s. First attempt was a pytest
temporary-parent setup error (87 setup errors, no strategy execution); corrected
the isolated directory and reran. After bridge edits, existing quant/native/live/
canonical research set: 100 passed in 26.88s. Later new pipeline checks and full
acceptance are recorded in CHECKPOINT.json/ACCEPTANCE.md after execution.

Real host preopen 09:19: Doctor PASS, account ready, model login READY, providers
responded; Yahoo stale and Nasdaq fresh public reference. Ledger version 0,
cash/book NAV100000, no holdings, previous canonical 2026-10-07 PAPER_NO_TRADE.
No ledger schema change, reset, daily run, broker action or forced time/date occurred.

Frozen dependency verification found 18 installed versions that differed from
the checked-in lock in the active worktree. The isolated environment was repaired
with uv 0.12.7 and `sync --frozen --group dev`; neither the lock nor the root
worktree environment changed. All 48 locked installed distributions now match
the lock; the bootstrap pip distribution brings the total to 49. Initial static
and targeted results preceding this repair are historical diagnostics, not the
final acceptance evidence. The first full frozen validation passed 990 tests in
221.17 seconds; the final status-report changes require a fresh full run.
