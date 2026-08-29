# Provider capability matrix

This matrix describes the current boundary, not a guarantee about future
vendors. UNVERIFIED means Meridian has not integrated or independently
validated that capability. No row below is execution-grade.

| Provider / source | Live | Historical | Point-in-time | Bid/Ask | Fundamentals | News | Macro | API key | Execution-grade | Research-grade | Current status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fake/replay providers | No | Yes (synthetic only) | No (HISTORICAL_REPLAY_UNSAFE) | No | Synthetic | Synthetic | Synthetic | No | No | No | Implemented for offline tests; not live data |
| TradingAgents internal tools | Yes (graph path) | No by default | UNVERIFIED | UNVERIFIED | Analyst-dependent | Analyst-dependent | Analyst-dependent | Provider-dependent | No (Meridian discards execution fields) | Qualitative research context | Optional pinned adapter; provenance is insufficient for executable signals |
| Future SEC/EDGAR | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | UNVERIFIED | No | No | UNVERIFIED | No | UNVERIFIED | Not connected |
| Future market quote provider | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | No | No | UNVERIFIED | No | UNVERIFIED | Not connected; execution quote authority remains separate |
| Future news provider | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | No | UNVERIFIED | No | UNVERIFIED | No | UNVERIFIED | Not connected |
| Future macro provider | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | No | No | UNVERIFIED | UNVERIFIED | No | UNVERIFIED | Not connected |

The project-owned evidence protocols expose capability metadata without leaking
vendor SDK types into Meridian domain models. A provider failure is recorded
per provider; it cannot fabricate a neutral or bullish signal.
