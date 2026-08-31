# Meridian Alpha — Gate 6A final report

## Production decision path

Gate 6A is mechanically exercised by the shared path:

`real quant -> certified SEC evidence -> CertifiedEvidenceView -> frozen
DeepSeek output -> EvidenceAuthorizationService -> CertifiedAgentSignal ->
AlphaFusion -> deterministic allocator -> RiskEngine -> reconciliation`.

The run is shadow-only and uses a sanitized synthetic Host-style account. The
production artifact is [gate6a-production-shadow-v10.json](../reports/gate6a-production-shadow-v10.json)
with a matching Markdown view.

| Check | Result |
| --- | --- |
| Production Alpha path | PASS (shared `ProductionShadowOrchestrator`) |
| Real quant | PASS for AAPL/NVDA from stored shadow diagnostics |
| Certified LLM | PASS: AAPL and NVDA frozen outputs authorize through the evidence gate |
| Production modifier | `0.18` for AAPL and NVDA; combined cap enforced |
| Final alpha changed | YES for both directional signals versus quant-only |
| MSFT | Explicit `ABSTAIN` / no certified replay signal |
| Allocation/risk/reconciliation | PASS in shadow mode; no execution authorization |

## Security certificate integrity

The captured primary-source Security Master contains 11/11 records. A sidecar
manifest verifies the capture-set digest, bounded-universe digest, each record
digest, source hashes/URIs, and historical identity intervals. The default
development registry remains non-authoritative; runtime authority is obtained
only by the explicit verified loader.

`CAPTURED = 11/11`; `ARTIFACT_VALID = yes`; `RUNTIME_AUTHORITATIVE = 11/11`
for the explicit shadow load. This does not change the default fixture.

## Fundamental availability and collisions

Comparative and derived fundamental objects carry the maximum acceptance time
of their inputs. Evidence bundles advertise that same maximum `available_at`,
so a delayed or future component cannot enter an earlier cutoff. Canonical
concept registry entries now declare precedence and component aggregation;
ambiguous same-period collisions are reported instead of being chosen by
response ordering. Long-term debt may aggregate current/non-current components
only when no reported combined total is present.

## FinRL-X and execution boundary

FinRL-X runtime and artifact are `MODEL_UNAVAILABLE`; no OOS-validated shadow
inference exists and promotion is `NO`. Legacy `VALIDATED_SHADOW` remains only
for explicit fixture compatibility and never counts as OOS validation.

Execution quote remains `TO_BE_SELECTED`; Host supervised smoke was not run.
There is no broker, Schwab connection, real account, order, fill, or automatic
promotion path.

## Validation

- Pytest: **234 passed**
- Ruff: **PASS**
- Pyright: **0 errors, 0 warnings**
- `git diff --check`: **PASS**

Known P0: **0**. Known P1: the execution quote provider and supervised Host
input remain pending; FinRL-X has no usable runtime/artifact. No release label
requiring those conditions is claimed.

Final authorization: **SHADOW / NOT AUTHORIZED FOR ENTRY**.
