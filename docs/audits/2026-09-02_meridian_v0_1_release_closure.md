# Meridian v0.1 release closure

## Baseline and final state

- Baseline: `9109917`.
- No tag was created.
- User-owned `reports/gate6g-quote-preflight.json` remains unstaged.
- `pyproject.toml` had an existing canonical console-script edit. This stage
  added the minimal Hatchling direct-reference setting required to build the
  declared optional TradingAgents Git dependency.

## Verified gates

- Python: 3.12.14.
- Dependency lock: `uv.lock` present, requires Python 3.12.
- Editable packaging: passed after the Hatchling setting; canonical
  `meridian version --json` succeeded.
- Fresh runtime: `meridian init --json` returned `INIT_COMPLETE`, schema 1.
- Fresh runtime doctor: PASS, 46 ms, `network_accessed=false`.
- Broker execution: disabled; source inventory found no broker action tool.

## Blocking release evidence

1. The existing MCP daily tools still call legacy `DailyAnalysisService` and
   repo-relative audit storage rather than `MeridianApplicationService`.
   CLI/MCP equivalence is therefore not established.
2. The fresh-runtime `data-status` public-provider request did not meet the
   bounded-runtime requirement in this environment (observed tool wall time
   approximately 9,192 seconds). This is an operational P0 even though the
   provider adapters declare request timeouts.
3. Public Yahoo/Stooq data is non-execution-grade; no certified execution
   quote exists. Historical PIT certification also remains blocked.
4. Forward evidence has append-only primitives but daily/scout advisory events
   are not yet safely wired to a production ledger.

## Release decision

`V0_1_OPERATIONAL_RC = BLOCKED`.

Meridian may be described only as manual-decision-support development
software. It is not a certified research engine, a proven-alpha product, an
execution-certified system, or an automated broker product.

## Prior evidence retained

The Stage C live DeepSeek smoke parsed a real structured response and correctly
abstained for an empty evidence packet; it did not grant economic or execution
authority. Stage B's public market smoke returned a truthful blocked result.
