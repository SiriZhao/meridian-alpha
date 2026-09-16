# Meridian daily research report

Run ID: `daily-b0d66daecc451f8a67d0a287`
Environment: **PASS**
Cache: **READY** (healthy)
Data Provider: **DATA_DEGRADED**; lanes: PRIMARY
Market Status: **OPEN**
Execution Mode: **DEGRADED_OPERATIONAL**
Runtime: **PASS**; Analysis: **BLOCKED_STALE_MARKET**
Forward evidence: **INSUFFICIENT_FORWARD_EVIDENCE**; maturity: **NOT_MATURE**; samples: 0.
Account freshness: **PASS**; Market freshness: **BLOCKED**
Research invocation: **NO_ACTION**; Decision: **NOT_RUN**
Research universe: **full**; eligible 3 -> research 3 -> deep analysis 3

## Data auto-retrieval

Initial completeness: **0.3846153846153846153846153846**
Final completeness: **0.6043956043956043956043956044**
Quality: **GOOD** (80/100)
Requirements: 23; retrieved: 11; sources: 9.
Unresolved blocking fields: none

## Recommendation readiness

Recommendation: **BLOCKED**
Research: **BLOCKED**
Manual execution: **BLOCKED**

EXECUTION = MANUAL
BROKER SUBMISSION = DISABLED

## Blockers

- REQUIRED_OPERATIONAL_MARKET_DATA_UNAVAILABLE
- MARKET_DATA_STATUS_BLOCKED
- MARKET_DATA_FRESHNESS_BLOCKED
- RESEARCH_STATUS_BLOCKED
- RESEARCH_FRESHNESS_UNKNOWN
- DECISION_PIPELINE_STATUS_NOT_RUN
- POLICY_GATE_STATUS_NOT_RUN
- REAL_INPUT_NOT_VERIFIED

## Input verification

Account freshness: **PASS**; novelty: **NEW**; age seconds: 1.604193.
Account provenance: **PASS**; diagnostic: ACCOUNT_SNAPSHOT_VALID.
Market freshness: **BLOCKED**; mode: OPERATIONAL_PUBLIC.

## Operator stages

| Stage | Status |
| --- | --- |
| Market | FAILED |
| Account | VERIFIED |
| Research | NO_ACTION |
| Decision | BLOCKED_STALE_MARKET |

## Gates

- ACCOUNT_READY: **PASS** — Fresh authoritative paper ledger observation
- SECURITY_READY: **NOT_RUN** — Operational sector metadata is not authoritative certification
- MARKET_READY: **BLOCKED** — Market observations must be fresh at decision time
- RESEARCH_READY: **BLOCKED** — Public model inference is advisory, not certified evidence
- QUOTE_READY: **BLOCKED** — Certified execution quote absent
- RISK_READY: **BLOCKED** — Deterministic projected portfolio validation
- RECONCILIATION_READY: **BLOCKED** — Reconciliation uses supplied facts; no fills inferred

## Research (MODEL_INFERENCE; advisory only)

Provider/model: CODEX_CLI/CLI_DEFAULT; provider evidence: CODEX_CLI; attempts: 1; diagnostic: CODEX_NO_ACTION.
Auth mode: **CHATGPT_MANAGED_CODEX**; reasoning: **medium**; schema: **PASS**; elapsed: **60703 ms**.
Research status: **NO_ACTION**; recommendation: **NO_ACTION**; confidence: **0**.

## Next actions

- Provide verifiable authorized Host source evidence; content hashes are not authentication.
- Supply fresh market observations if freshness is blocked.
- Run certified research and policy gates before recommendation readiness.
- Manual entry additionally requires a certified execution quote and sealed authority.

## Research-only draft — NOT AUTHORIZED FOR MANUAL ENTRY

