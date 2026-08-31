# Meridian Alpha — Gate 6B / 6C final report

## Five-equity certified shadow

Gate 6B extended the accession-linked SEC Company Facts lane to AAPL, MSFT,
NVDA, META, and GOOGL. Each ticker was processed through exact accession and
`acceptanceDateTime` certification, canonical metrics, comparable periods, and
derived metrics. The resulting daily run uses the production AlphaFusion path,
the verified Security Master loader, and a synthetic Host-style account. It
remains `SHADOW / NOT AUTHORIZED FOR ENTRY`.

Frozen replay was used for the previously validated AAPL and NVDA DeepSeek
outputs; MSFT, META, and GOOGL remained explicit abstentions. No directional
diversity was manufactured and no dislocation model call was required by the
bounded screen.

## Host contract and self-test

`schemas/examples/real-host-envelope-template.json` is a valid sanitized
`HostAccountSnapshotEnvelope` example. `meridian host-smoke <file>` validates
the same schema, rejects sensitive keys, loads the explicitly verified
11-symbol Security Master artifact when present, normalizes the account, and
runs the shared analysis service. Fixture self-tests cover complete, partial,
stale, future, duplicate, external-trade, and partial-fill states. No
externally authorized real Host envelope was supplied, so the status remains
`READY_FOR_SUPERVISED_HOST_INPUT`; `REAL_HOST_DATA_SMOKE_COMPLETE` is not
claimed.

## Execution quote and manual-entry release candidate

Provider-neutral `ExecutionQuoteProvider` contracts and read-only Alpaca and
Polygon candidate adapters are implemented. `meridian quote-preflight` emits
only configured/reachable/feed/quote/certificate metadata and never prints
credentials. With no local provider configuration and no supervised plan/feed
evidence, both candidates remain `TO_BE_SELECTED`; Yahoo remains a research
price source only. The strict quote validator and deterministic limit-price
policy are available for certified fixtures, but no production quote
certificate exists. Consequently `QUOTE_READY = NO` and `MANUAL_ENTRY_READY =
NO`.

## Safety and readiness

| Area | Status |
| --- | --- |
| Runtime Security Master | Explicit artifact load: 11/11 authoritative |
| Real Host input | Not supplied; supervised-input package ready |
| Real execution quote | Not configured/certified |
| Manual ticket | Test fixture only; not production-ready |
| Broker / Schwab | None / not connected |
| Real orders | Zero |
| FinRL-X promotion | No |

The detailed machine-readable provider-health and fixture results are in
`reports/gate6c-provider-health.json` and
`reports/gate6c-provider-health.md`. Gate 6B coverage and daily shadow
artifacts are in `reports/gate6b-five-equity-fundamentals.*` and
`reports/gate6b-daily-shadow-v11.*`.

## Legitimate labels

- `FINRLX_SHADOW_CHALLENGER_READY` is not claimed here because the runtime and
  OOS-validated artifact remain unavailable.
- `READY_FOR_SUPERVISED_HOST_INPUT`
- `READY_FOR_LONGER_SHADOW_OBSERVATION`

`REAL_HOST_DATA_SMOKE_COMPLETE`, `EXECUTION_QUOTE_CERTIFIED`, and
`READY_FOR_MANUAL_ENTRY` are not claimed.

Known P0: **0**. Known P1: no external Host input and no certified execution
quote provider configuration. No push or tag was created.
