# Meridian Alpha — Gate 6G final report

Generated 2026-08-31 from `scripts/gate6g_supervised_rc.py` at the Gate 6F
checkpoint. The runner uses only explicitly supplied sanitized Host input and
bounded read-only provider diagnostics. It does not inspect browser state or
credential files, and it has no broker surface.

## Status

**BLOCKED_REAL_HOST_INPUT** — no externally authorized sanitized Host envelope
was supplied.

| Gate | Result | Evidence |
| --- | --- | --- |
| Real Host input present | NO | `reports/gate6g-host-smoke.json` |
| Real Host smoke | NOT RUN | only synthetic self-tests were run |
| Quote provider configuration | NOT CONFIGURED | `reports/gate6g-quote-preflight.json` |
| Live quote probe | NOT RUN | probe is opt-in and no local configuration exists |
| Execution quote certificate | NO | candidate capabilities remain `execution_quote_grade=false` |
| Manual readiness certificate | NOT ISSUED | both external gates are blocked |
| Manual entry | NO | no production draft can be emitted |

## Mechanical safety evidence

The fixture battery passed complete, partial, stale, future, duplicate-idempotent,
duplicate-conflict, external-trade, and partial-fill cases. A certified quote
fixture can produce only a `TEST_FIXTURE` draft with `status=NOT_EXECUTED`; it
is not real-ready and does not mutate account state. Quote validation rejects
missing, inverted, wide, stale, future, wrong-identity, and unsupported asset
class observations. VIX/index capability is separate from equity/ETF coverage.

## Provider posture

Alpaca Market Data and Polygon are read-only candidates. Their endpoint,
credential, feed/plan, timestamp, session, rate-limit, licensing, and manual-
ticket semantics are not proven in this environment. No capability certificate
was issued and no provider failover was attempted. Official source references
and the dated review are recorded in
`docs/execution-quote-provider-certification.md`.

## Final safety declaration

- **REAL HOST INPUT PRESENT:** NO
- **REAL HOST SMOKE:** NOT COMPLETE
- **QUOTE PROVIDER CONFIG:** NONE DETECTED
- **QUOTE LIVE PROBE:** NOT RUN
- **EXECUTION QUOTE CERTIFIED:** NO
- **MANUAL READINESS CERTIFICATE:** BLOCKED
- **READY_FOR_MANUAL_ENTRY:** NO
- **BROKER:** NONE
- **SCHWAB:** NOT CONNECTED
- **REAL ORDERS:** ZERO
- **KNOWN P0:** 0
- **KNOWN P1:** missing externally authorized Host input; missing certified execution-quote capability

Legitimate labels earned by this gate: `READY_FOR_SUPERVISED_HOST_INPUT` and
`BLOCKED_EXECUTION_QUOTE_CERTIFICATION` (not `REAL_HOST_DATA_SMOKE_COMPLETE`,
`EXECUTION_QUOTE_CERTIFIED`, or `READY_FOR_MANUAL_ENTRY`).