# Meridian integration and release closure — Stage C

## Baseline

- Baseline SHA: `002a02d`.
- User-owned `reports/gate6g-quote-preflight.json` remained modified and was
  neither read, edited, staged, nor committed.

## MCP inventory

The existing `src/meridian/mcp_server.py` is the only registered MCP server.
It currently registers account validation, old daily-analysis, provider/audit
inspection, manual-draft inspection, and decision explanation tools.

- **REGISTERED / LEGACY:** `run_daily_analysis` and
  `run_host_daily_analysis` call the older `DailyAnalysisService` and a
  repo-relative audit store.
- **UNREGISTERED canonical surface:** ApplicationService-backed health,
  data-status, sanitized snapshot validation, daily, Dip Scout, latest report
  and forward-status tools.
- **DUPLICATE:** provider-health and target-inspection aliases.
- **FORBIDDEN / absent:** no broker login, credential, order submission,
  cancellation, or execution tool is registered.

## Safety decision

The attempted thin MCP registrations were deliberately not applied.  The
initial handler shape accepted arbitrary local paths, would have returned a
full application payload, and would have marked persistent daily analysis as
read-only.  That is not an acceptable MCP boundary.  A safe Stage D contract
must accept only a sanitized envelope/payload, require an explicit persistence
guard for a report-producing daily run, and return a fixed redacted schema.
Existing MCP behaviour was left intact rather than introducing an unsafe
parallel path.

`MeridianApplicationService.latest_report()` was added as a redacted runtime
read method.  Its fixed summary excludes filesystem paths, raw account data,
credentials, and orders, and always declares `EXECUTION = MANUAL` and
`BROKER SUBMISSION = DISABLED`.

## Live intelligence smoke

`DEEPSEEK_API_KEY` was configured (the value was not read or logged).  One
real, bounded request was made to `deepseek-v4-flash` at
`2026-09-02T13:41:23Z`, with one AAPL packet containing no invented evidence
and an explicit empty-evidence reason.

- latency: `6046 ms`;
- strict Meridian structured-schema parse: passed;
- result: `INSUFFICIENT_GROUNDING / MODEL_ABSTAIN`.

This is the correct fail-closed outcome for an evidence-free probe.  It did
not create an order, economic recommendation, or ForwardPrediction.  LLM
status remains advisory/shadow.

## Forward ledger

The existing append-only ledger was inspected. It rejects changed prediction
IDs, immature outcomes and outcome overwrite. Mock/test predictions are not
written by the smoke. Wiring real advisory daily/scout events into a guarded
production ledger remains incomplete.

## Verification

- intelligence/LLM/manual-authority focus: `35 passed`;
- full suite: `300 passed in 16.33s`;
- Ruff, Pyright, compileall and diff check: passed.

## Stage D release-gate inputs

1. MCP must receive an ApplicationService method for sanitized in-memory
   account input; no arbitrary file paths.
2. Persisting `analyze_daily` must have an explicit user-visible guard and
   return a fixed redacted schema.
3. Legacy MCP daily handlers need thin-wrapper migration/removal only after
   CLI/Application/MCP equivalence tests pass.
4. Production forward evidence requires a real advisory-event append gate and
   provider/model breakdown without allowing mocks into evidence.
5. Public market provider availability and execution-quote authority remain
   independent product-release blockers.
