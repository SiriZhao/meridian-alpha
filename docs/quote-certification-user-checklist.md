# Execution-quote certification user checklist

This checklist prepares a read-only provider review. Never paste API keys,
secrets, OAuth tokens, Authorization headers, account identifiers, or raw
provider responses into ChatGPT. Configure credentials only through an approved
local secret manager/environment outside Git.

## Alpaca Market Data candidate

- Confirm the account/plan is entitled to the documented stock/ETF market-data
  feed needed for manual decision support; do not infer entitlement from a
  successful HTTP response.
- Confirm the selected feed’s bid/ask/trade coverage, real-time or delayed
  semantics, regular/pre/post-market behavior, halt handling, currency, and
  rate limits in current official documentation.
- Use read-only market-data credentials only. Trading endpoints and order
  permissions are out of scope and must not be enabled.
- Codex preflight checks only configured/not-configured state, transport/auth
  outcome (without values), endpoint/feed metadata, timestamp/session fields,
  freshness, and certificate eligibility.

## Polygon candidate

- Confirm the account/plan and stocks/ETF feed entitlement required for the
  intended symbols, including whether quotes are real-time or delayed.
- Confirm bid/ask/trade event timestamp semantics, session mapping, halt
  behavior, currency, rate limits, licensing/manual-ticket posture, and any
  asset-class limitations in current official documentation.
- Use read-only credentials only; never share them in chat or enable trading
  access.
- Codex performs the same sanitized preflight and strict quote-instance checks;
  connectivity alone cannot issue a certificate.

## Certificate must prove

The selected provider/feed must have a reviewable capability certificate tying
it to the exact quote: provider identity, feed/plan, supported assets and
sessions, event timestamp semantics, freshness SLA, currency, rate-limit and
licensing posture, source-document hashes, validity window, and policy version.
Every quote instance must then pass symbol/currency, bid/ask, spread, timestamp,
future/stale, session, halt, and provider-match validation. No silent provider
failover or bid/ask averaging is allowed.