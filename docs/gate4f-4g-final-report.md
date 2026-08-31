# Meridian Alpha — Gate 4F / 4G final report

## Safety posture

Known P0: **none**. No broker writes, Schwab connection, real account, or real
orders were introduced. Yahoo remains a research-market-price source only.

## Security Master

The bounded live capture in `reports/gate4f-security-master.json` obtained
primary-source response hashes and retrieval timestamps for **11/11** symbols:
SEC submissions for AAPL/MSFT/NVDA/META/GOOGL, official sponsor pages for
SPY/QQQ/SGOV/GLD/TLT, and official Cboe VIX documentation. The promotion service
checks source kind/host, exact content hash, legal identity fields, CIK (where
applicable), and a historical effective interval. The development fixture
registry remains deliberately **0/11 authoritative** until a caller explicitly
loads those captured certificates; a current-source interval is not evidence
for earlier history.

Provider symbols remain separate from legal identity. Unknown or conflicting
identity and historical intervals outside the captured range are blocked.

## Host

`host-smoke` now uses the shared sanitized normalization path and emits all
eight explicit gates as `PASS`, `FAIL`, or `DEGRADED`. The generated report
contains only source name, snapshot ID, timestamps, coverage, currency, counts,
warnings, and a provenance digest. No externally authorized sanitized Host
envelope was supplied in this run, so the status is
`READY_FOR_SUPERVISED_HOST_INPUT` and real-data smoke is incomplete.

## Execution quote

`docs/execution-quote-provider-certification.md` records a bounded review of
Polygon.io and Alpaca as candidates and rejects Yahoo for ticket pricing. No
API key, documented plan, timestamp/session proof, licensing posture, or
provider configuration was available to issue an execution capability
certificate. The strict `ExecutionQuote` hierarchy and pure validator are
implemented and tested, but the provider status remains `TO_BE_SELECTED`.
Consequently `MANUAL_ENTRY_READY = NO`; no manual ticket is executable.

## Validation

The new identity, host-readiness, and quote adversarial tests cover fake
authorities, missing provenance, historical bounds, sensitive Host keys,
missing/inverted/wide/stale/future/wrong-identity quotes, extended-hours
ambiguity, and deterministic limit-price ownership. Existing Gate 2.6–3B and
Gate 5 tests remain in the suite.

Legitimate labels for this checkpoint:

- `AUTHORITATIVE_SECURITY_MASTER_READY` (11/11 captured in the bounded review
  artifact; runtime fixture promotion remains explicit)
- `READY_FOR_SUPERVISED_HOST_INPUT`
- `READY_FOR_LONGER_SHADOW_OBSERVATION`

Not claimed: `REAL_HOST_DATA_SMOKE_COMPLETE`, `EXECUTION_QUOTE_CERTIFIED`, or
`READY_FOR_MANUAL_ENTRY`.

