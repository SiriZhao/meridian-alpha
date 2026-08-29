# MVP validation

## Executed locally

- `pytest`: contract, policy, no-look-ahead, stale-account, zero-capital, and
  synthetic-capital invariants.
- `ruff check .` and `pyright`.
- Local MCP `/health` returned 200.
- A local streamable-MCP `initialize` request to `/mcp` returned 200 and
  advertised protocol/tool capabilities.

## Scenario A — synthetic Schwab state, $0 cash and no holdings

The daily CLI returned `NO_CAPITAL` with `orders = []`.

## Scenario B — synthetic $50,000 cash and no holdings

The deterministic full pipeline is tested with fake, timestamped quotes and
fake evidence-backed research. It verifies budgeted buy drafts and limit prices.
This is synthetic validation only; it is not a production market-data test.

## Remaining blockers to production

There is no verified production market-data provider, authorized account-data
connector, validated FinRL-X model artifact, walk-forward evaluation dataset,
or hosted HTTPS deployment. The MCP `run_daily_analysis` tool deliberately
returns `BLOCKED_STALE_MARKET` for non-zero accounts until a verified provider
exists.
