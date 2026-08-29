# Gate 2.6 Safety Convergence

## IMPLEMENTED / TESTED

- Every BUY updates cumulative projected cash, holdings, and market value before constraint checks.
- Only an authorization-issued `CertifiedAgentSignal` may influence executable Alpha Fusion.
- PIT statuses are closed-enum values with an explicit executable allowlist.
- Executable citations require an explicit authoritative `available_at <= as_of`.
- Provider capabilities and item certification are checked together.
- TEST and REPLAY never issue executable research certificates.
- Historical live research is rejected outside configured as-of tolerance.
- Candidate feature timestamps are required for graph invocation; missing/stale features are deferred.
- READY manual tickets require `AccountSyncState.SYNCED`.
- Review archives exclude env files, credentials, VCS metadata, caches, databases, and runtime state.

## NOT CONNECTED

No live data providers, DeepSeek calls, TradingAgents live graph calls, Schwab, FinRL-X execution, or broker write capability are connected.

## FUTURE GATE 3B

Production evidence providers and supervised live normalization require separate review and PIT certification.
