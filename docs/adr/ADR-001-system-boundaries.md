# ADR-001: System boundaries and no-execution policy

- **Status:** Accepted
- **Date:** 2026-08-28

## Context

Meridian Alpha is intended to assist a user who holds a US-equity brokerage
account. Account state is sensitive and order submission has material financial
consequences. Research frameworks may include simulated or live execution
facilities that are outside the product's safety contract.

## Decision

Meridian Alpha accepts a normalized, newly supplied `AccountSnapshot` as an
input and produces only a manual limit-order ticket as an output. The core has
no direct Schwab Trading API dependency, no broker client, and no order write
capability.

All executable-looking output is fail-closed behind verified account and market
freshness. LLMs provide qualitative research only; deterministic code owns
allocation, risk, reconciliation, quantities, and limit prices. Account data is
sanitized and non-persistent by default.

TradingAgents and FinRL-X are optional adapters behind project-owned protocols.
No upstream source is copied. FinRL-X execution modules are prohibited from the
Meridian import graph.

## Consequences

Users must obtain current account data through an authorized mechanism and
manually enter every order. Meridian does not know whether a ticket filled until
the next account snapshot. This reduces automation convenience but preserves a
clear human-approval boundary and prevents false portfolio truth.
