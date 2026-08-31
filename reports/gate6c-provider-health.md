# Gate 6C provider health and release-candidate self-test

| Area | Status | Detail |
| --- | --- | --- |
| Security Master | PASS | runtime authoritative 11/11 |
| Real Host input | NOT SUPPLIED | synthetic fixtures only; READY_FOR_SUPERVISED_HOST_INPUT |
| Execution quote | TO_BE_SELECTED | no capability certificate |
| Manual entry | NO | requires real account and certified quote |

## Provider diagnostics

- `alpaca-market-data`: configured=False, endpoint_reachable=False, certificate_eligible=False; NO_LOCAL_PROVIDER_CREDENTIAL_CONFIGURED
- `polygon-market-data`: configured=False, endpoint_reachable=False, certificate_eligible=False; NO_LOCAL_PROVIDER_CREDENTIAL_CONFIGURED

## Fixture self-test

- `complete`: **PASS** — SYNCED
- `partial`: **PASS** — PARTIAL
- `stale`: **PASS** — PARTIAL
- `future`: **PASS** — HOST_ACCOUNT_AS_OF_IN_FUTURE
- `duplicate`: **PASS** — DUPLICATE_SNAPSHOT_ID_CONTENT_CONFLICT
- `external_trade`: **PASS** — reconciliation fixture parsed
- `partial_fill`: **PASS** — reconciliation fixture parsed

No broker, Schwab, credential, account identifier, or order surface is used.
