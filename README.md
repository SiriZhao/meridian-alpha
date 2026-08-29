# Meridian Alpha

`meridian` is an AI-assisted, long-only portfolio decision system for US equities.

It turns a newly supplied, normalized brokerage `AccountSnapshot` and verified
market data into a deterministic target portfolio and **manual limit-order
ticket**. It never submits, places, or executes brokerage orders.

## Status

This repository currently contains the project constitution, architecture, and
development toolchain only (Step 0). It does not contain brokerage integration,
market-data adapters, research engines, allocation, or order-planning logic.

## Safety boundary

- The current account snapshot is the sole truth for holdings and cash.
- Recommendations are never treated as fills.
- Stale or unverifiable account/market data must block executable output.
- Human approval and manual entry are required for every real order.
- No broker credentials, API keys, or account numbers belong in this repository.

## Development

Python 3.12 is the supported runtime.

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
uv run pyright
```

See [architecture.md](docs/architecture.md),
[product-contract.md](docs/product-contract.md), and
[build-state.md](docs/build-state.md).

## Upstream research integrations

TradingAgents and FinRL-X will be optional adapters, pinned by commit and
isolated from the domain core. See the compatibility record in
[build-state.md](docs/build-state.md). Their Apache-2.0 licenses are compatible
with this repository's planned dependency strategy; no upstream source code is
copied here.

## Non-advice notice

Meridian Alpha is a research and decision-support system, not investment,
legal, tax, or trading advice. Outputs remain drafts for user review and manual
entry.
