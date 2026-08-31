# Gate 6G Host smoke

Status: **READY_FOR_SUPERVISED_HOST_INPUT**
Real Host input present: **False**

Synthetic fixture scenarios are TEST_ONLY and do not establish external authorization.

- `complete`: **PASS** — SYNCED
- `partial`: **PASS** — PARTIAL
- `stale`: **PASS** — PARTIAL
- `future`: **PASS** — HOST_ACCOUNT_AS_OF_IN_FUTURE
- `duplicate_identical`: **PASS** — REGISTERED,DUPLICATE_IDEMPOTENT
- `duplicate_conflict`: **PASS** — SNAPSHOT_ID_CONFLICT:DUPLICATE_SNAPSHOT_ID_CONTENT_CONFLICT
- `external_trade`: **PASS** — sanitized reconciliation fixture
- `partial_fill`: **PASS** — sanitized reconciliation fixture