# Failure matrix

| Failure | Expected state |
| --- | --- |
| Account stale/partial/conflicting | BLOCKED_STALE_ACCOUNT or ANALYSIS_ONLY; no ticket |
| Unknown security / quote / historical row | fail closed; no inferred identity/value |
| SEC/news/macro unavailable | explicit provider failure or insufficient grounding; never neutral alpha |
| Evidence authorization/citation failure | no CertifiedAgentSignal |
| DeepSeek/TradingAgents unavailable | explicit unavailable/abstain; no retry storm |
| FinRL-X manifest/artifact unavailable | MODEL_UNAVAILABLE; deterministic allocator remains production path |
| Risk or order-pricing failure | DRAFT/blocked; no manual-ready result |