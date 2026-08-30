# Product readiness matrix

| Capability | Implemented | Real | PIT certified | Shadow | Executable | Tested | Current blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Account truth | Yes | No | N/A | Yes | No | Yes | READY_FOR_SUPERVISED_HOST_INPUT; no real envelope |
| Security identity | Yes | Partial | No | Yes | No | Yes | 0/11 authoritative provenance records; 11 bounded development records |
| Market research data | Yes | Yes | No | Yes | No | Yes | Yahoo is excluded from certified prompts |
| Execution quote | No | No | No | No | No | Yes | TO_BE_SELECTED; Yahoo is last-only |
| Historical OHLCV | Yes | Yes | No | Yes | No | Yes | availability certification |
| Corporate actions | Yes | No | No | Yes | No | Yes | source certification |
| Fundamentals / events | Yes | Yes | Partial | Yes | No | Yes | AAPL/NVDA/MSFT SEC accession path only |
| News / macro | Contract | No | No | No | No | Yes | provider certification |
| TradingAgents | Contract | No | No | Optional | No | Yes | not exercised; qualitative-only |
| DeepSeek grounding | Yes | Yes | Yes | Yes | No | Yes | shadow-only; default disabled |
| CertifiedAgentSignal | Yes | Yes | Yes | Yes | No | Yes | model returned neutral, no alpha contribution |
| Dislocation research | Yes | No | Requires certified evidence | Yes | No | Yes | no eligible deterministic candidate in V5 |
| Quant / deterministic allocator | Yes | Mixed | N/A | Yes | No | Yes | execution quote |
| FinRL-X challenger | Yes | No | No | Yes | No | Yes | model artifact absent; not promoted |
| Risk / reconciliation | Yes | No | N/A | Yes | No | Yes | execution quote |
| ChatGPT Host/MCP | Yes | No | N/A | Yes | No | Yes | sanitized host-smoke harness; supervised input pending |
| Broker | No | No | N/A | No | No | Yes | intentionally absent |