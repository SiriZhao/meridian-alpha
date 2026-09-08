# Schwab-Paper

## Purpose

Schwab-Paper is Meridian's persistent, authoritative **paper** portfolio. It
is a local internal ledger, not a Schwab integration, a broker-authenticated
account, or evidence for real-Host production acceptance. It exists so the
strategy, risk and portfolio layers use one continuous account state without
requiring daily JSON editing.

The initial state is created once:

- Account: `Schwab-Paper`
- Currency: USD
- Initial cash: USD 100,000.00
- Positions, orders, fills and realized P&L: empty / zero

Ordinary daily operation never resets this state.

## Run

```powershell
.\scripts\run_meridian.ps1 paper run --account Schwab-Paper --json
```

This is not a second investment pipeline. It performs:

```text
SQLite paper ledger → fresh PAPER_LEDGER envelope → canonical daily
→ live public market → advisory research → deterministic decision/gates
→ paper-only eligible fills → atomic ledger update → NAV/report
```

The temporary envelope is generated from current cash, positions, cost basis,
ledger version and observation time. It passes the normal snapshot validator.
An unchanged portfolio observed later is new paper evidence; resubmitting the
same old export is a replay.

## Controls

Paper execution is allowed only when the canonical run has fresh public market
inputs during a NYSE regular session, validated advisory research, a completed
deterministic decision and no portfolio/risk constraint violation. It uses the
existing long-only, cash, position, concentration and turnover controls.
`policies/paper.yaml` supplies conservative 5 bps slippage, USD 1.00 commission
per order and SPY benchmark defaults.

Each fill records the public reference price, simulated fill price, fees,
provider, run ID and order ID. The fill, cash, position, average cost, realized
P&L and ledger event commit in one SQLite transaction. Same-account/same-day
execution is idempotent: a second invocation may refresh reports but cannot
place duplicate paper fills.

Cash, NAV, realized/unrealized P&L, cumulative return, drawdown, turnover,
fees and SPY comparison are persisted. Dividends are `NOT_IMPLEMENTED` and are
never estimated.

## Safety boundary

`PAPER_EXECUTION_ONLY` is distinct from recommendation readiness, manual
execution authority and broker execution. Fresh Yahoo or any other public
source is still a `PUBLIC_RESEARCH_QUOTE`, never a certified execution quote.
No broker SDK, login, order or fill API exists. A missing credential, stale
market, closed session, provider failure or invalid research response yields a
structured blocked report; it never falls back to fixtures or historical LLM
output.

## Inspection and reset

```powershell
.\scripts\run_meridian.ps1 paper status --account Schwab-Paper --json
.\scripts\run_meridian.ps1 paper history --account Schwab-Paper --json
.\scripts\run_meridian.ps1 paper trades --account Schwab-Paper --json
.\scripts\run_meridian.ps1 paper init --account Schwab-Paper --cash 100000 --currency USD --json
```

`paper init` preserves an existing account. Resetting is intentionally separate:

```powershell
.\scripts\run_meridian.ps1 paper reset --account Schwab-Paper --confirm-reset Schwab-Paper --json
```

The daily command and the Skill never call reset.
