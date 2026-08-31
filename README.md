# Meridian Alpha

`meridian` is an AI-assisted, long-only portfolio decision system for US equities.

It turns a newly supplied, normalized brokerage `AccountSnapshot` and verified
market data into a deterministic target portfolio and **manual limit-order
ticket**. It never submits, places, or executes brokerage orders.

## Status

The repository contains the Meridian decision-support core, bounded public-data
shadow adapters, certified SEC fundamentals, and replay-safe research contracts.
It still contains no brokerage integration, broker writes, real account, or
order-submission surface. Gate 6B/6C shadow output remains explicitly
`SHADOW / NOT AUTHORIZED FOR ENTRY`; no production execution quote is
certified.

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

The supervised Host contract can be checked with
`meridian host-smoke <sanitized-envelope.json>`. Candidate quote configuration
is inspected with `meridian quote-preflight`; this command never prints
credentials and does not certify a provider by connectivity alone.

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

## Gate 6D/6E release-candidate posture

The current application has explicit `TEST`, `REPLAY`, `SHADOW_LIVE`, and
`MANUAL_DECISION_SUPPORT` profiles. The durable long-shadow ledger and offline
replay/soak foundation are available. Reports always lead with `BLOCKED`,
`ANALYSIS_ONLY`, `SHADOW`, or `READY_FOR_MANUAL_ENTRY`. The current release
candidate is `SHADOW / NOT AUTHORIZED FOR ENTRY`: no real Host envelope or
execution-quote certificate is present, FinRL-X is `MODEL_UNAVAILABLE`, and no
broker or Schwab authentication/write surface exists.
## V1 daily-shadow release (Gate 6H/6I)

The supported user-facing command is `meridian daily`. It runs the shared
sanitized analysis path and writes `runs/<date>/<run_id>/` artifacts plus
append-only shadow ledgers. Profiles are `TEST`, `REPLAY`, `SHADOW_LIVE` (explicit
opt-in), and `MANUAL_DECISION_SUPPORT`; there is no `AUTO_EXECUTION` profile.
TradingAgents is qualitative context only, while DeepSeek `CertifiedEvidenceView`
is the certified research lane. FinRL-X is optional and deferred (`MODEL_UNAVAILABLE`
is acceptable). A manual draft requires a READY seven-gate
`ManualReadinessCertificate` and a certified `ExecutionQuote`; no broker or
Schwab surface exists.

## Meridian Alpha V1 release candidate

V1 is code-feature complete for bounded US-equity shadow observation. The
production path is certified SEC fundamentals plus Quant, certified DeepSeek
research, deterministic AlphaFusion, allocation, risk, reconciliation, a
shadow ledger, and a sealed manual-authority framework. TradingAgents remains
qualitative context only; FinRL-X is deferred (`MODEL_UNAVAILABLE` is valid).

Current external/observation blockers are an authorized real Host smoke, a
certified read-only execution quote, and the minimum shadow observation period.
No Schwab execution, broker login, broker writes, or real orders exist.

### Install as Agent Skill

Download and verify [`dist/meridian-alpha-skill-v1.zip`](dist/meridian-alpha-skill-v1.zip)
with [`dist/meridian-alpha-skill-v1.sha256`](dist/meridian-alpha-skill-v1.sha256),
then install it through the ChatGPT Skills UI where available. See
[`docs/chatgpt-mobile-skill-install.md`](docs/chatgpt-mobile-skill-install.md).
GitHub is distribution, not automatic ChatGPT installation.
