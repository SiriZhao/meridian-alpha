# Provider capability matrix

This matrix describes the current boundary, not a guarantee about future
vendors. UNVERIFIED means Meridian has not integrated or independently
validated that capability. No row below is execution-grade.

| Provider / source | Live | Historical | Point-in-time | Bid/Ask | Fundamentals | News | Macro | API key | Execution-grade | Research-grade | Current status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fake/replay providers | No | Yes (synthetic only) | No (HISTORICAL_REPLAY_UNSAFE) | No | Synthetic | Synthetic | Synthetic | No | No | No | Implemented for offline tests; not live data |
| Stooq public CSV (shadow) | UNVERIFIED | No | No | No (`BID_ASK_UNAVAILABLE`) | No | No | No | No | No | UNVERIFIED | Implemented shadow adapter; not certified or executable |
| Yahoo chart public (shadow) | Yes (current chart) | Yes (chart history) | No (delay/PIT unverified) | No (`BID_ASK_UNAVAILABLE`) | No | No | No | No | No | No | Implemented real shadow adapter; not certified or executable |
| TradingAgents internal tools | Yes (graph path) | No by default | UNVERIFIED | UNVERIFIED | Analyst-dependent | Analyst-dependent | Analyst-dependent | Provider-dependent | No (Meridian discards execution fields) | Qualitative research context | Optional pinned adapter; provenance is insufficient for executable signals |
| SEC Company Facts adapter (code-only) | Yes (public endpoint) | Yes (current response) | No (historical availability unverified) | No | Yes | No | No | No | No | No | Implemented but not authorized for executable research |
| Future market quote provider | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | No | No | UNVERIFIED | No | UNVERIFIED | Not connected; execution quote authority remains separate |
| Future news provider | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | No | UNVERIFIED | No | UNVERIFIED | No | UNVERIFIED | Not connected |
| Future macro provider | UNVERIFIED | UNVERIFIED | UNVERIFIED | No | No | No | UNVERIFIED | UNVERIFIED | No | UNVERIFIED | Not connected |

The project-owned evidence protocols expose capability metadata without leaking
vendor SDK types into Meridian domain models. A provider failure is recorded
per provider; it cannot fabricate a neutral or bullish signal.

Gate 3B.1 adds a typed `MarketDataCapabilityCertificate`; omitted or unknown capabilities default to false. The Stooq row is an observation source only and cannot authorize executable research.
Gate 3B.3 adds the code-only SEC Company Facts adapter plus synthetic replay news and macro adapters; none is independently PIT-certified or executable.
