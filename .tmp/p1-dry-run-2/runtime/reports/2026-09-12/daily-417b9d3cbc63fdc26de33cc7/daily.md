# Meridian daily research report

Run ID: `daily-417b9d3cbc63fdc26de33cc7`
Environment: **PASS**
Cache: **READY** (healthy)
Data Provider: **DATA_DEGRADED**; lanes: NONE
Market Status: **CLOSED**
Execution Mode: **SAFE_ANALYSIS**
Runtime: **PASS**; Analysis: **NO_ACTION**
Forward evidence: **INSUFFICIENT_FORWARD_EVIDENCE**; maturity: **NOT_MATURE**; samples: 0.
Account freshness: **PASS**; Market freshness: **PASS**
Research invocation: **RESEARCH_OFFLINE**; Decision: **PASS**
Research universe: **reduced**; eligible 4 -> research 3 -> deep analysis 3

## Data auto-retrieval

Initial completeness: **NOT_RUN**
Final completeness: **NOT_RUN**
Quality: **NOT_RUN** (0/100)
Requirements: 0; retrieved: 0; sources: 0.
Unresolved blocking fields: none

## Recommendation readiness

Recommendation: **BLOCKED**
Research: **BLOCKED**
Manual execution: **BLOCKED**

EXECUTION = MANUAL
BROKER SUBMISSION = DISABLED

## Blockers

- ACCOUNT_PROVENANCE_UNKNOWN
- PROVIDER_PROVENANCE_DEGRADED
- RESEARCH_STATUS_NOT_RUN
- RESEARCH_FRESHNESS_UNKNOWN
- POLICY_GATE_STATUS_DEGRADED
- REAL_INPUT_NOT_VERIFIED

## Input verification

Account freshness: **PASS**; novelty: **NEW**; age seconds: 2.340922.
Account provenance: **UNKNOWN**; diagnostic: ACCOUNT_SNAPSHOT_VALID.
Market freshness: **PASS**; mode: FIXTURE.

## Operator stages

| Stage | Status |
| --- | --- |
| Market | PASS |
| Account | VERIFIED |
| Research | RESEARCH_OFFLINE |
| Decision | NO_ACTION |

## Gates

- ACCOUNT_READY: **BLOCKED** — Authenticated fresh Host source required
- SECURITY_READY: **DEGRADED** — Operational sector metadata is not authoritative certification
- MARKET_READY: **PASS** — Market observations must be fresh at decision time
- RESEARCH_READY: **NOT_RUN** — Public model inference is advisory, not certified evidence
- QUOTE_READY: **BLOCKED** — Certified execution quote absent
- RISK_READY: **PASS** — Deterministic projected portfolio validation
- RECONCILIATION_READY: **PASS** — Reconciliation uses supplied facts; no fills inferred

## Research (MODEL_INFERENCE; advisory only)

Provider/model: GPT_NATIVE_V1/codex-default; provider evidence: NONE; attempts: 0; diagnostic: none.
Auth mode: **CHATGPT_MANAGED_CODEX**; reasoning: **medium**; schema: **FAIL**; elapsed: **0 ms**.
Research status: **NOT_RUN**; recommendation: **NO_ACTION**; confidence: **NOT_AVAILABLE**.

## Research intelligence (advisory only)

Research status: **RESEARCH_OFFLINE**; Decision status: **RESEARCH_ONLY**; Execution status: **BLOCKED_MARKET_CLOSED**.
Research data: **PASS**; Execution data: **PASS**.
Evidence coverage: **6**; system confidence: **0.8879**; LLM self-confidence: **None**.
Primary thesis (GPT OPINION): GPT reasoning unavailable.
Counter-thesis (GPT OPINION): 
What changed: **NEW**.
Disagreement score: **0.0**.
FACT = normalized structured evidence; MODEL INFERENCE = deterministic analytics; GPT OPINION = schema-validated advisory reasoning.
Execution availability remains independently gated. GPT research has no order, price, sizing, or broker authority.

## Next actions

- Provide verifiable authorized Host source evidence; content hashes are not authentication.
- Supply fresh market observations if freshness is blocked.
- Run certified research and policy gates before recommendation readiness.
- Manual entry additionally requires a certified execution quote and sealed authority.

## Research-only draft — NOT AUTHORIZED FOR MANUAL ENTRY

