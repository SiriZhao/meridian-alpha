# Trusted Web Market Data

Date: 2026-09-11  
Status: **BLOCKED_WITH_EVIDENCE**

The local implementation is accepted. The real Astra acceptance is blocked:
the single fresh `gpt-6-astra` request at medium reasoning returned
`CODEX_RATE_LIMITED` before Skill discovery, browsing, or MCP calls. It was not
retried.

## Active architecture

```text
LOCAL CACHE → YAHOO STRUCTURED DATA → ASTRA TRUSTED WEB EVIDENCE → UNKNOWN
```

Stooq has been removed from active source code, provider registration, security
provider symbols, runtime fallback construction, research preparation and
current operator guidance. Historical reports are retained unchanged. Yahoo
remains public research data only; it cannot become an execution quote.

`TrustedWebMarketEvidence` and `TrustedSourcePolicy` are project-owned typed
contracts. Astra may browse after a stale/missing Yahoo result, then submits
compact URL-backed facts to `validate_market_evidence`. Meridian does not browse
or call another LLM. The validator rejects invalid URLs, untrusted domains,
future/post-cutoff observations, duplicate submissions, malformed numerical
facts and narrative historical bars. It accepts a Tier A fact or two independent
Tier A/B sources, exposes conflicts without averaging, and always returns
`execution_authority=NONE`.

Historical OHLCV must be an explicit machine-readable table. It is never
reconstructed from prose; absence is `HISTORICAL_DATA_UNAVAILABLE`.

## Verification

- Full suite: **474 passed** in 63.25 seconds.
- Focused trusted-web contract tests: 9 passed.
- Ruff: PASS.
- Pyright: PASS, 0 errors and 0 warnings.
- Dependency integrity: PASS.
- Doctor: PASS; source and installed Skill hashes match.
- Deterministic coverage includes Yahoo-only runtime construction, stale and
  unavailable behavior, trusted Tier A acceptance, two-source Tier B
  corroboration, untrusted/missing URL/future evidence rejection, duplicate
  sources, conflicts, currency mismatch, historical-table requirements and
  `execution_authority=NONE`.

## Real Astra attempt

- Fresh thread: `01a090cf-60cd-79b0-a9e0-70f61cfcab8e`.
- Requested model: `gpt-6-astra`; reasoning: `medium`.
- Prompt: “Use Meridian to research GOOGL. If Meridian structured market data
  is unavailable or stale, use trusted web sources to obtain research-grade
  market context. Do not invent market data. Show every source used.”
- Result: `CODEX_RATE_LIMITED` before any tool call.

No web source, market value, evidence reference, conflict, historical table or
research synthesis was fabricated as a substitute. Once quota is available,
run one fresh session with the same prompt and capture the Skill/tool/browse
trace before upgrading this status.
