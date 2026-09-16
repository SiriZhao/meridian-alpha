# Meridian Daily — Schwab-Paper

Status: **PAPER_BLOCKED**
Canonical run: `daily-b0d66daecc451f8a67d0a287`
Environment: **PASS**
Cache: **READY** (healthy)
Data Provider: **DATA_DEGRADED**; lanes: PRIMARY
Market Status: **OPEN**
Execution Mode: **DEGRADED_OPERATIONAL**
Research Universe: **full**; eligible 3 -> research 3 -> deep analysis 3

## Data auto-retrieval

Initial completeness: **0.3846153846153846153846153846**
Final completeness: **0.6043956043956043956043956044**
Quality: **GOOD** (80/100)
Requirements: 23; retrieved: 11; sources: 9.
Failed or unresolved: SPY:FUNDAMENTALS:latest_fundamentals, MSFT:FUNDAMENTALS:latest_fundamentals, NVDA:FUNDAMENTALS:financial_statements, MSFT:FUNDAMENTALS:financial_statements, NVDA:EARNINGS:earnings_commentary, MSFT:EARNINGS:earnings_commentary, SPY:NEWS:material_events, NVDA:NEWS:material_events, MSFT:NEWS:material_events, MACRO:MACRO:macro_context, MSFT:EARNINGS:recent_earnings_commentary, NVDA:EARNINGS:recent_earnings_commentary

## Portfolio

NAV: **$100000.0000**
Cash: **$100000.0000**
Market value: **$0.0000**
Realized P&L: **$0.0000**

## Performance

Daily return: **None**
Since inception: **0.0000**
SPY since inception: **None**
Excess return: **None**
Drawdown: **0.0000**


### Evidence sources (expandable)

- SPY / current_market_snapshot: operational-provider-chain @ canonical-market-stage (confidence 0.85, validated PASS)
- NVDA / current_market_snapshot: operational-provider-chain @ canonical-market-stage (confidence 0.85, validated PASS)
- MSFT / current_market_snapshot: operational-provider-chain @ canonical-market-stage (confidence 0.85, validated PASS)
- PORTFOLIO / portfolio_context: meridian @ meridian-account-snapshot-validation (confidence 1, validated PASS)
- MERIDIAN / strategy_policy: meridian-policy @ E:\CSDIY\Vibe Coding Project\meridian-alpha\policies\strategy_profile.json (confidence 1, validated PASS)
- MSFT / daily_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- NVDA / daily_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- SPY / daily_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- SPY / benchmark_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- NVDA / latest_fundamentals: sec-companyfacts @ https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json (confidence 0.90, validated PASS)
- VIX / vix: yahoo-macro @ https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d (confidence 0.75, validated PASS)
- MSFT / return_1d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / return_5d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / return_20d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / return_60d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / return_1y: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / return_ytd: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / sma20: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / sma50: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / sma200: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / ema20: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / ema50: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / rsi14: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / atr14: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / realized_volatility_20d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / realized_volatility_60d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / average_volume_20d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / relative_volume: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / drawdown: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / max_drawdown: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / distance_52w_high: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / distance_52w_low: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / gap: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / beta_60d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / rolling_correlation_60d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / relative_performance_spy_20d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- MSFT / relative_performance_spy_60d: meridian-derived-market-features-v1 @ derived-from:ev_f54ca05569eaa16d9bdac5c5 (confidence 0.85, validated PASS)
- NVDA / return_1d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / return_5d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / return_20d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / return_60d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / return_1y: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / return_ytd: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / sma20: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / sma50: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / sma200: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / ema20: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / ema50: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / rsi14: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / atr14: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / realized_volatility_20d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / realized_volatility_60d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / average_volume_20d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / relative_volume: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / drawdown: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / max_drawdown: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / distance_52w_high: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / distance_52w_low: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / gap: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / beta_60d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / rolling_correlation_60d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / relative_performance_spy_20d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- NVDA / relative_performance_spy_60d: meridian-derived-market-features-v1 @ derived-from:ev_a4037168a8af991a4b8d5be6 (confidence 0.85, validated PASS)
- SPY / return_1d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / return_5d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / return_20d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / return_60d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / return_1y: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / return_ytd: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / sma20: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / sma50: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / sma200: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / ema20: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / ema50: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / rsi14: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / atr14: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / realized_volatility_20d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / realized_volatility_60d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / average_volume_20d: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / relative_volume: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / drawdown: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / max_drawdown: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / distance_52w_high: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / distance_52w_low: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)
- SPY / gap: meridian-derived-market-features-v1 @ derived-from:ev_f2128af2b54f3cfeee278349 (confidence 0.85, validated PASS)

## Positions

- No open positions.

## Market

Status: **FAILED**; session: **OPEN**.
Public observations are research quotes only; quote certification remains BLOCKED.

## Today's Decisions

Deterministic decision: **BLOCKED_STALE_MARKET**.
Paper order intents: **0**.

## Risk

Existing long-only, cash reserve, position, concentration and turnover constraints were applied.

## Today's Paper Trades

- No paper fills.

## Research

Research: **CODEX / GPT**
Status: **NO_ACTION**
Model: **CLI_DEFAULT**
Reasoning: **medium**
Structured validation: **PASS**
Confidence: **0**
Recommendation: **NO_ACTION**
Elapsed: **60703 ms**
Diagnostic: **CODEX_NO_ACTION**

## Forward Evidence

Status: **INSUFFICIENT_FORWARD_EVIDENCE**. Evidence never grants automatic promotion.

## Gates

- ACCOUNT_READY: **PASS** — Fresh authoritative paper ledger observation
- SECURITY_READY: **NOT_RUN** — Operational sector metadata is not authoritative certification
- MARKET_READY: **BLOCKED** — Market observations must be fresh at decision time
- RESEARCH_READY: **BLOCKED** — Public model inference is advisory, not certified evidence
- QUOTE_READY: **BLOCKED** — Certified execution quote absent
- RISK_READY: **BLOCKED** — Deterministic projected portfolio validation
- RECONCILIATION_READY: **BLOCKED** — Reconciliation uses supplied facts; no fills inferred

## Readiness

Paper execution: **PAPER_BLOCKED**
Recommendation readiness: **BLOCKED**
Manual authority: **BLOCKED**
Quote certification: **BLOCKED** — public research quotes are not certified execution quotes.

## Blockers

- PAPER_EXECUTION_BLOCKED_MARKET_DATA
- PAPER_EXECUTION_BLOCKED_RESEARCH_NO_ACTION
- PAPER_EXECUTION_BLOCKED_DECISION_BLOCKED_STALE_MARKET

## Next action

- Inspect canonical report and retry only during a regular session with fresh public data and validated advisory research.

PAPER ACCOUNT ONLY. BROKER SUBMISSION = DISABLED. PUBLIC QUOTES = UNCERTIFIED.
