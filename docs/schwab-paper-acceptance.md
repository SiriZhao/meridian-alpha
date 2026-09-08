# Schwab-Paper runtime acceptance

## Verdict

**ENGINEERING VERIFIED; LIVE PAPER EXECUTION NOT YET VERIFIED.**

The paper ledger, snapshot bridge, canonical daily integration, atomic fills,
accounting, reporting, idempotency, Windows launcher and installed wheel are
verified by regression and isolated runtime evidence. This does not claim a real
broker account, a certified execution quote, manual authority or real-Host
production acceptance.

## Verified evidence

- 384 tests passed; Ruff passed; Pyright reported 0 errors and 0 warnings.
- SQLite v2 → v3 preserves existing user data and adds paper account, position,
  fill, ledger, idempotency and NAV tables in the existing AuditStore database.
- `Schwab-Paper` initializes once at USD 100,000.00, preserves state across
  restart, creates fresh `PAPER_LEDGER` observations and rejects old snapshots
  as replays.
- Fills atomically update cash, positions, average cost, realized P&L and ledger
  sequence. Long-only, cash, order, turnover and idempotency controls are tested.
- The PowerShell launcher and the built wheel successfully initialized/read the
  paper account from outside the checkout.

## Actual canonical run

`run_meridian.ps1 paper run --account Schwab-Paper --json` was executed in an
isolated runtime. It auto-created the account, invoked canonical daily and
wrote canonical plus paper JSON/Markdown reports. The runtime completed, but
correctly returned `PAPER_BLOCKED`:

- NYSE session: `CLOSED`.
- Yahoo: `STALE`.
- Stooq: `UNAVAILABLE` with HTTP 404.
- Research: `RESEARCH_INPUT_NOT_READY`; no LLM HTTP request was sent.
- Decision: `BLOCKED_STALE_MARKET`.
- Fills: zero.

This is expected fail-closed behavior. The evidence is recorded in
[the machine acceptance artifact](../reports/schwab-paper-runtime-acceptance.json).

## Next evidence required

Run the unchanged paper command in a NYSE regular session. Fresh public market
observations and a validated canonical advisory-research response are required
before paper fills can be verified. Public data will still remain uncertified
for manual/broker execution, and the existing real-Host acceptance remains
independently blocked.
