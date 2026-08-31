# Meridian Alpha V1 product readiness

Status: **V1_BLOCKED_ON_EXTERNAL_INPUT**

| Capability | Implemented | Real data | PIT safe | Production path | Shadow tested | Manual dependency | Blocker |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| Account truth | TRUE | FALSE | TRUE | TRUE | TRUE | TRUE | real externally authorized Host snapshot |
| Security Master | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE | — |
| Market/research data | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE | execution-grade quote remains uncertified |
| Certified SEC fundamentals | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE | — |
| Quant | TRUE | TRUE | TRUE | TRUE | TRUE | FALSE | — |
| DeepSeek certified research | TRUE | TRUE | TRUE | TRUE | TRUE | TRUE | research calls require explicit opt-in or exact replay |
| AlphaFusion/allocator/risk/reconciliation | TRUE | FALSE | TRUE | TRUE | TRUE | TRUE | — |
| Dislocation shadow | TRUE | FALSE | TRUE | TRUE | TRUE | FALSE | observation only |
| ExecutionQuote boundary | TRUE | FALSE | TRUE | TRUE | TRUE | TRUE | provider capability certificate |
| Manual ticket boundary | TRUE | FALSE | TRUE | TRUE | TRUE | TRUE | Host + certified quote |
| Replay/shadow ledger | TRUE | FALSE | TRUE | TRUE | TRUE | FALSE | — |
| MCP/Skill/Chinese report | TRUE | FALSE | TRUE | TRUE | TRUE | FALSE | — |
| FinRL-X | TRUE | FALSE | TRUE | FALSE | FALSE | FALSE | MODEL_UNAVAILABLE / optional post-v1 |

Core v1 is feature-complete for shadow observation. Real Host input and an execution-quote capability certificate remain external blockers.

FinRL-X: `MODEL_UNAVAILABLE` is acceptable and formally deferred post-v1. TradingAgents remains qualitative context only; DeepSeek certified evidence is the production research path.

No broker writes, Schwab authentication, real orders, or automatic execution occurred.
