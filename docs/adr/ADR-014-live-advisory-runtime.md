# ADR-014: Windows runtime recovery and research-only live advisory

2026-09-14. Accepted for this hotfix.

The canonical paper run fails at ResearchMemory.save with WinError 17. The
LocalAppData runtime has EFS attributes and a same-directory rename probe fails,
although the old doctor read/write probe passes. Preserve this runtime; use an
explicit MERIDIAN_HOME on a filesystem verified to support atomic replacement.
Do not downgrade failed atomic updates to non-atomic overwrites. The ordinary
default remains LocalAppData, and explicit environment configuration wins.

Add a live-advisory application entry point reusing the project-owned quote,
GPT-native research, deterministic allocation and risk boundaries. It reads the
existing paper ledger or a supplied fresh sanitized Host snapshot. It never
creates paper fills, order tickets, broker connections or execution authority.
Account context is ephemeral and excluded from public input hashes and reports.
No raw account snapshot is newly persisted. Public evidence and invocation
diagnostics remain auditable. Existing external-host verification remains intact.

LLM opinions may express BUY/ADD/HOLD/WAIT/TRIM/SELL/AVOID independently of risk
eligibility. Numerical reference levels come only from observed prices and
deterministic rules. Allocation/risk remain independent from model prose.
The baseline allocation factor is observed daily return. Research also consumes
the existing point-in-time feature engine's completed-session SMA, RSI, ATR,
volatility and relative-performance features. Original public OHLCV inputs are
atomically saved with their hashes for independent recalculation. No FinRL-X
model is invented or represented as invoked;
scenario probabilities are explicitly uncalibrated model opinions.

LIVE describes an observed timestamp age <=90 seconds, with declared provider
delay taking precedence. It is not a certified execution quote or a claim of
consolidated exchange entitlement. Reports recheck freshness at publication.
Stale, future, cached or missing observations cannot pass live acceptance.
