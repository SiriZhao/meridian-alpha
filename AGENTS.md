# Meridian Alpha project constitution

## Scope

Meridian Alpha is a US-equity, AI-assisted portfolio decision system. Its
terminal boundary is a manual limit-order ticket for a human to enter at their
broker. It has no brokerage execution capability and must never grow one.

## Permanent principles

1. Schwab actual account state is the source of truth.
2. Never assume yesterday’s recommended orders were filled.
3. Never infer fills from recommendations.
4. Every trading day starts from a newly supplied AccountSnapshot.
5. No look-ahead data is permitted.
6. LLM output never directly determines share quantity or limit price.
7. Portfolio sizing and order generation must be deterministic.
8. Human approval is required for every real order.
9. No automatic brokerage execution is permitted.
10. If account or market data freshness cannot be verified, executable order output must be blocked.
11. Sensitive account data must not be persisted by default.
12. Never fabricate FinRL-X model outputs.
13. Never fabricate missing market/account data.

## Hard prohibitions

- Do not add broker execution, broker login, or brokerage-write code.
- Do not directly couple the core to the Schwab Trading API.
- Do not add, print, read, commit, or log credentials, tokens, account numbers,
  or other secrets. Use environment/secret-manager references only when a
  later, explicitly approved integration needs them.
- Do not make research-agent prose the source of order quantities, position
  sizes, or prices.
- Do not bypass freshness gates, risk checks, reconciliation, or manual
  approval.
- Do not persist raw AccountSnapshot data by default.

## Required dependency and interface discipline

- The core depends on project-owned domain protocols, never on a broker SDK,
  TradingAgents, FinRL-X, or a data-provider SDK.
- External frameworks are optional adapters, pinned by version/commit and
  invoked behind explicit interfaces.
- All future market data must carry provenance and timestamps; unavailable or
  unverified data is represented explicitly, never invented.
- Changes to system boundaries require an ADR.

## Quality gates

Run the applicable checks before handoff:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
```

Do not push a remote or create a release tag unless the user explicitly asks.
