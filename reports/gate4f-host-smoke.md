# Gate 4F Host smoke

Status: **READY_FOR_SUPERVISED_HOST_INPUT**
Real externally authorized Host input: **True**

| Gate | Status | Reason |
| --- | --- | --- |
| ACCOUNT_READY | FAIL | Host snapshot is stale or unknown |
| SECURITY_READY | PASS | Authoritative Security Master certification is required |
| MARKET_READY | FAIL | Current market research data is required |
| RESEARCH_READY | FAIL | Certified research is required for the selected profile |
| QUOTE_READY | FAIL | Certified execution quote is required |
| RISK_READY | FAIL | Deterministic risk checks have not passed |
| RECONCILIATION_READY | FAIL | Current account truth has not been reconciled |
| MANUAL_ENTRY_READY | FAIL | All account, identity, quote, risk, and reconciliation gates must pass |

No account numbers, credentials, tokens, or raw connector payloads are included.
