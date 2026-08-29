# ADR-007 — Real Provider Certification and Shadow Data (Gate 3B.5)

## Decision

Public Yahoo chart data may be acquired through Meridian-owned quote and raw
OHLCV adapters for bounded SHADOW diagnostics. SEC Company Facts remains a
code-only fundamentals adapter with unverified historical filing availability.
A provider certification registry records capabilities explicitly; omitted or
unknown capabilities are false.

Real observations are never promoted solely by successful HTTP responses.
Security identity, timestamp, freshness, PIT, provenance and provider
capability gates remain mandatory. The first real-data daily run uses a
synthetic account, skips live TradingAgents/DeepSeek, emits zero certified
signals and remains `SHADOW / NOT AUTHORIZED FOR ENTRY`.

## Consequences

- Last-only public quotes are never treated as execution-grade bid/ask data.
- Historical OHLCV is raw and shadow-only; current retrieval does not prove
  historical information availability.
- Provider disagreement or failure is explicit and isolated.
- Host-account integration remains blocked until supervised provenance and PIT
  certification are complete.
