# Gate 6E release-candidate report

Status: **SHADOW / NOT AUTHORIZED FOR ENTRY**

The release candidate converges on one safe daily application boundary with
explicit `TEST`, `REPLAY`, `SHADOW_LIVE`, and `MANUAL_DECISION_SUPPORT` profiles.
There is no automatic execution profile. Reports begin with an unambiguous
status, and the Chinese mobile V3 report is available for host rendering.

The long-shadow ledger, replay battery, provider-health matrix, and bounded
offline soak are durable/reproducible. FinRL-X remains an isolated optional
challenger: no compatible runtime or OOS-validated artifact was found, so its
status is `MODEL_UNAVAILABLE` and production continues with the deterministic
allocator. Security certificates are only promoted by explicit verified-artifact
loading. Execution quote certification and real Host smoke remain blocked until
their external prerequisites are supplied.

No broker, Schwab authentication, credential storage, broker write, real order,
or automatic model-promotion path was added.

## Mechanical status

- PRODUCTION ALPHA PATH: shared deterministic quant → certified research → AlphaFusion → allocator → risk → reconciliation
- REAL QUANT: yes in existing Gate 6A/6B shadow artifacts
- CERTIFIED LLM: frozen/replay-certified artifacts available; no new live call required
- PRODUCTION MODIFIER: non-zero in validated AAPL/NVDA artifacts
- FINAL ALPHA CHANGED: yes in the authoritative AlphaFusion result
- REAL LLM ALPHA BREAKTHROUGH: previously certified in Gate 6A; preserved
- SECURITY CAPTURE: 11/11; explicit artifact loader returns 11 authoritative
- REAL HOST SMOKE: not run; no externally authorized envelope supplied
- EXECUTION QUOTE: TO_BE_SELECTED; certificate absent
- MANUAL ENTRY READY: NO
- REPLAY CACHE: PASS; historical replay: PASS; soak: 100 deterministic cycles
- FINRL-X RUNTIME: MODEL_UNAVAILABLE
- FINRL-X ARTIFACT: none
- FINRL-X OOS / WALK-FORWARD / REAL SHADOW: not run
- FINRL-X PROMOTED: NO
- PYTEST: 242 passed
- RUFF: pass
- PYRIGHT: pass
- KNOWN P0: 0
- KNOWN P1: real Host input absent; execution quote certificate absent; FinRL-X runtime/artifact unavailable
- KNOWN P2: none recorded

Broker: NONE · Schwab: NOT CONNECTED · Real orders: ZERO
