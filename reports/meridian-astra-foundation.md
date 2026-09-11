# Meridian Astra Foundation — Final Acceptance

Date: 2026-09-11  
Status: **PARTIAL**

## Verified outcome

The local Astra foundation and the real GPT-6 Astra host integration both ran.
The final state is PARTIAL, not PASS, because the fresh host discovered the
installed Meridian Skill through the host Skill catalog but explicitly reported
that it could not read the complete installed `SKILL.md` through a non-shell
host reader. This is a host-observability limitation, not a substituted claim.

No broker login, account connection, order submission, amendment, cancellation,
or credential handling was attempted.

## Verified runtime

- Branch: `astra/canonical-production-workflow`
- Baseline HEAD before the evidence-only commit: `7a7eff5410febc78fb210be249c88f892cecebef`
- Project Python: 3.12.10 from `.venv`
- System Python: 3.14.3; not selected
- Codex CLI host: 0.154.0
- Meridian native Codex compatibility check: 0.153.4 (minimum 0.153.0)
- Source/installed Skill tree hash:
  `c54bf6b3bf19cf0c44487d4fdb6f1849f664f8b9459ac03d4c3e9e68204dbc72`
- Local doctor: PASS
- Full tests: 439 passed
- Ruff: PASS
- Pyright: 0 errors, 0 warnings

The full local doctor actively verified writable RuntimePaths, database schema
3, cache atomic replacement, installed Skill hash equality, and MCP discovery.

## Real fresh Astra evidence

Post-fix fresh Codex session:

- session id: `01a0902b-02fa-7633-8fc6-8bea25581505`
- model: `gpt-6-astra`
- reasoning effort: `high`
- sandbox: `read-only`
- Skill: discovered from the host Skill catalog as evidence-grounded US-equity
  research and manual-investment decision support

The model actually invoked:

`runtime_status`, `company_facts`, `market_snapshot`, `forward_evidence`,
`portfolio_context`, `risk_analysis`, `quant_metrics`, `account_snapshot`,
`validate_account_snapshot`, and `validate_host_account_snapshot`.

`runtime_status` passed in the read-only host. Its cache state was
`NOT_PROBED_READ_ONLY_HOST` with no I/O error: local `meridian doctor --json`
remains the active writable-path verifier. This prevents a deliberately
read-only host from falsely diagnosing its sandbox as a production cache ACL
failure.

MSFT company research used official SEC evidence. Current price, liquidity, and
quantitative outputs were reported UNKNOWN when public market inputs were stale
or unavailable; no value was invented. The host also reported insufficient
forward evidence rather than inferring a performance conclusion.

The sanitized in-memory portfolio scenario remained advisory only. The stale
snapshot scenario produced consistent fail-closed outcomes across all three
relevant tools: `valid=false`, `ACCOUNT_SNAPSHOT_STALE`, and
`execution_authority=NONE`.

## Minimal fixes verified

- `runtime_status` now runs a transparent non-mutating diagnostic view for a
  read-only MCP host; `meridian doctor --json` retains active write probes.
- Legacy snapshot validators now reject stale or unsynchronized data instead
  of reporting `valid=true`, and explicitly return `execution_authority=NONE`.
- `market_snapshot` now returns the caller-declared analysis cutoff in its MCP
  metadata while preserving the established live collection cutoff semantics.

## Remaining blockers to PASS

1. The fresh host cannot expose a full installed-Skill-file read through its
   non-shell tool surface. It confirmed discovery and executed the Skill's
   described read-only workflow, but `skill_file_read` was explicitly false.
2. Current public market data was stale/unavailable in the smoke. This safely
   yields UNKNOWN research fields and blocks execution; it is not bypassed.
3. No fresh verified real account context was supplied, and Forward Evidence
   has no mature samples. Both remain non-executable by design.

## Safety result

All real host scenarios retained `execution_authority=NONE`. No broker
execution surface was added or invoked.