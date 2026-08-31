# Gate 5E reliability soak

Mode: `OFFLINE_REPLAY` · cycles: **8** · external calls: **0** · retries: **0**

All scenarios remain explicit. Provider outages fail closed (or produce an
explicit degraded diagnostic where the product contract permits it); no outage
is silently neutralized. Frozen LLM replay is hash/cutoff/citation checked and
does not call DeepSeek.

| Area | Result |
| --- | --- |
| Cache load integrity | PASS — schema/content/file/record hashes and duplicate conflict rejection |
| Historical cutoff matrix | PASS (contract matrix) — 11 curated cases |
| Property/invariant tests | PASS |
| FinRL-X missing/bad artifact | `MODEL_UNAVAILABLE` / explicit fail closed |
| Provider health | PASS — five-state typed health, missing is `UNVERIFIED` |
| Performance/call budget | PASS — zero calls and retries in offline mode; live latency not measured |

Known P0: **0**. Known P1: FinRL-X runtime/artifact unavailable, execution
quote authority `TO_BE_SELECTED`, and no real sanitized Host envelope.
