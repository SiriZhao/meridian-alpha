# Product readiness matrix — Gate 6A (plus prior gates)

`IMPLEMENTED` describes a Meridian contract or adapter boundary; `REAL` and
`PIT CERTIFIED` describe observed evidence, not intent. No row authorizes a
broker action.

| Capability | IMPLEMENTED | REAL | PIT CERTIFIED | SHADOW | EXECUTABLE | TESTED | BLOCKER |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Account truth | Yes | No | N/A | Yes | No | Yes | No real Host envelope; supervised input pending |
| Security identity | Yes | Yes (11 bounded primary-source captures) | Current-source interval only | Yes | No | Yes | Default development fixture remains non-authoritative; explicit verified artifact load required |
| Market research data | Yes | Yes | No | Yes | No | Yes | Yahoo remains research-shadow only |
| Execution quote | Contract | No | No | Yes | No | Yes | TO_BE_SELECTED; Yahoo rejected; no certified bid/ask authority or adapter config |
| Historical OHLCV | Yes | Yes | No | Yes | No | Yes | provider availability/PIT certification |
| Corporate actions | Contract | No | No | Yes | No | Yes | source certification pending |
| Fundamentals | Yes | Yes | Yes | Yes | No | Yes | bounded SEC AAPL/NVDA/MSFT coverage |
| Company events | Yes | Yes | Per observation | Yes | No | Yes | SEC filing-presence lane only |
| News | Contract | No | No | Yes | No | Yes | PIT/licensing semantics unverified |
| Macro | Contract | No | No | Yes | No | Yes | vintage provider configuration unavailable |
| TradingAgents | Contract | No | No | Yes | No | Yes | qualitative-only; live smoke not run |
| DeepSeek grounding | Yes | Yes (frozen AAPL/NVDA outputs) | Yes | Yes | No | Yes | live/replay output remains shadow-only |
| CertifiedAgentSignal | Yes | Yes (AAPL/NVDA) | Yes | Yes | No | Yes | MSFT replay is explicit ABSTAIN |
| Dislocation | Yes | No | Requires certified view | Yes | No | Yes | no eligible certified candidate in last run |
| Quant | Yes | Yes (AAPL/NVDA diagnostics) | N/A | Yes | No | Yes | shadow analysis only |
| Deterministic allocator | Yes | Yes | N/A | Yes | No | Yes | production path remains shadow-only |
| FinRL-X challenger | Yes | No | No | Yes | No | Yes | MODEL_UNAVAILABLE; no OOS-validated artifact/runtime; promotion remains NO |
| Risk | Yes | No | N/A | Yes | No | Yes | manual quote authority absent |
| Reconciliation | Yes | No | N/A | Yes | No | Yes | requires next fresh account snapshot |
| Manual ticket | Contract | No | N/A | Yes | No | Yes | Quote authority and supervised account absent; deterministic draft remains NOT_EXECUTED |
| Host/MCP | Yes | No | N/A | Yes | No | Yes | Explicit gates implemented; no externally authorized sanitized Host input supplied |
| Broker | No | No | N/A | No | No | Yes | intentionally absent |
| Replay integrity | Yes | Yes (local cache/replay artifacts) | N/A | Yes | No | Yes | none; live provider health remains explicit |
| Production Alpha decision path | Yes | Yes (Gate 6A V10 shadow) | Yes | Yes | No | Yes | no execution authorization |
