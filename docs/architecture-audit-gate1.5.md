# ARCHITECTURE AUDIT — Gate 1.5

## Critical

- No automatic brokerage capability found. Runtime source contains no broker write endpoint or credential handling.
- Fail-closed status invariants are enforced: no-capital produces no orders; READY requires priced orders; NO_ACTION is explicit.

## High (fixed)

- Account and quote timestamp ages are enforced independently from freshness enums.
- Fresh market marks are separated from brokerage quantity/cash truth through `ValuedAccountState`; NAV discrepancy tolerance gates execution.
- Order sizing now precedes limit attachment and uses worst-case BUY caps. Same-day SELL proceeds are not used for BUY affordability.
- Projected portfolio validation, max single-order NAV, and max daily turnover are enforced deterministically.
- Sector checks require explicit security metadata; SPY is represented as a diversified ETF fixture.
- Evidence is structured with provenance and point-in-time timestamps.
- MCP and CLI use the same `DailyAnalysisService`; MCP remains read-only.

## Medium

- The development metadata registry is synthetic and must be replaced by a verified point-in-time security master before live use.
- Fractional shares remain disabled in the MVP planner.
- Production market-data and research providers are intentionally not configured.

## Low

- SQLite audit timestamps are informational strings; decision hashes and idempotency remain authoritative.
- Risk modifications use immutable model copies and are bounded by validated target contracts.

## Verification

- 36 deterministic tests pass.
- Ruff and Pyright pass with zero findings.
- Scenario A ($0 account) returns `NO_CAPITAL` with no orders.
- Scenario B ($50,000 cash) completes the synthetic pipeline under fixture data.
- Scenario C uses fresh quote marks for decision NAV while preserving broker-reported equity; a $2,500 discrepancy exceeds the $25 tolerance and cannot be READY.

No real API, LLM, broker, or live market-data provider was connected.
