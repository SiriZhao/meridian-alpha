# Meridian Daily — Schwab-Paper

Status: **PAPER_BLOCKED**
Canonical run: `daily-8ab2ebf564ef9e16d6a4106b`
Environment: **PASS**
Cache: **READY** (healthy)
Data Provider: **PASS**; lanes: PRIMARY
Market Status: **OPEN**
Execution Mode: **NORMAL**
Research Universe: **reduced**; eligible 4 -> research 3 -> deep analysis 3

## Data auto-retrieval

Initial completeness: **0.3846153846153846153846153846**
Final completeness: **0.9230769230769230769230769231**
Quality: **HIGH** (94/100)
Requirements: 13; retrieved: 12; sources: 11.
Failed or unresolved: SPY:FUNDAMENTALS:latest_fundamentals

## Portfolio

NAV: **$100000.0000**
Cash: **$100000.0000**
Market value: **$0.0000**
Realized P&L: **$0.0000**

## Performance

Daily return: **None**
Since inception: **0.0000**
SPY since inception: **0.0000**
Excess return: **0.0000**
Drawdown: **0.0000**


### Evidence sources (expandable)

- SPY / current_market_snapshot: operational-provider-chain @ canonical-market-stage (confidence 0.85, validated PASS)
- AAPL / current_market_snapshot: operational-provider-chain @ canonical-market-stage (confidence 0.85, validated PASS)
- NVDA / current_market_snapshot: operational-provider-chain @ canonical-market-stage (confidence 0.85, validated PASS)
- PORTFOLIO / portfolio_context: meridian @ meridian-account-snapshot-validation (confidence 1, validated PASS)
- MERIDIAN / strategy_policy: meridian-policy @ E:\CSDIY\Vibe Coding Project\meridian-alpha\policies\strategy_profile.json (confidence 1, validated PASS)
- AAPL / daily_ohlcv_1y: resilient-historical-chain @ yahoo (confidence 0.85, validated PASS)
- NVDA / daily_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- SPY / daily_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- SPY / benchmark_ohlcv_1y: yahoo @ yahoo (confidence 0.85, validated PASS)
- AAPL / latest_fundamentals: sec-companyfacts @ https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json (confidence 0.90, validated PASS)
- NVDA / latest_fundamentals: sec-companyfacts @ https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json (confidence 0.90, validated PASS)
- VIX / vix: yahoo-macro @ https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d (confidence 0.75, validated PASS)
- AAPL / return_1d: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / return_5d: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / return_20d: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / sma20: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / ema20: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / rsi14: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / atr14: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / realized_volatility_20d: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / average_volume_20d: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / relative_volume: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / drawdown: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / max_drawdown: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / gap: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
- AAPL / relative_performance_spy_20d: meridian-derived-market-features-v1 @ derived-from:ev_92de25fc89a023d4f2b724ab (confidence 0.85, validated PASS)
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

Status: **PASS**; session: **OPEN**.
Public observations are research quotes only; quote certification remains BLOCKED.

## Today's Decisions

Deterministic decision: **NO_ACTION**.
Paper order intents: **0**.

## Risk

Existing long-only, cash reserve, position, concentration and turnover constraints were applied.

## Today's Paper Trades

- No paper fills.

## Research

Research: **CODEX / GPT**
Status: **CODEX_TIMEOUT**
Model: **codex-default**
Reasoning: **medium**
Structured validation: **FAIL**
Confidence: **NOT_AVAILABLE**
Recommendation: **NO_ACTION**
Elapsed: **0 ms**
Diagnostic: **CODEX_TIMEOUT**

## Forward Evidence

Status: **INSUFFICIENT_FORWARD_EVIDENCE**. Evidence never grants automatic promotion.

## Gates

- ACCOUNT_READY: **PASS** — Fresh authoritative paper ledger observation
- SECURITY_READY: **DEGRADED** — Operational sector metadata is not authoritative certification
- MARKET_READY: **PASS** — Market observations must be fresh at decision time
- RESEARCH_READY: **BLOCKED** — Public model inference is advisory, not certified evidence
- QUOTE_READY: **BLOCKED** — Certified execution quote absent
- RISK_READY: **PASS** — Deterministic projected portfolio validation
- RECONCILIATION_READY: **PASS** — Reconciliation uses supplied facts; no fills inferred

## Readiness

Paper execution: **PAPER_BLOCKED**
Recommendation readiness: **BLOCKED**
Manual authority: **BLOCKED**
Quote certification: **BLOCKED** — public research quotes are not certified execution quotes.

## Blockers

- PAPER_EXECUTION_BLOCKED_RESEARCH_CODEX_TIMEOUT

## Next action

- Inspect canonical report and retry only during a regular session with fresh public data and validated advisory research.

PAPER ACCOUNT ONLY. BROKER SUBMISSION = DISABLED. PUBLIC QUOTES = UNCERTIFIED.
