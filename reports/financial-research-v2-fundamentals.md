# Meridian Financial Research V2 — Phase 2: Fundamentals and Valuation Evidence

Status: **BLOCKED_WITH_EVIDENCE** (implementation and local focused checks pass; the required real host scenario did not complete because the fresh Codex host could not resolve the Meridian MCP server).

## Delivered implementation

- Replaced the active small ticker-to-CIK maps with `SECTickerResolver`, which reads SEC's official `company_tickers.json`, caches exact resolutions, and rejects missing or ambiguous symbols.
- `SECCompanyFactsNumericProvider` now resolves CIK through that source and retains resolved company identity. The legacy accession-certified compatibility provider uses the same resolver.
- Added `SHARES_OUTSTANDING` to the canonical SEC metric registry.
- Upgraded the Skill-facing read-only `company_facts` tool. It now follows: SEC ticker identity → SEC Company Facts raw observations → exact SEC submissions accession metadata → `acceptance_datetime` certification → cutoff-safe deterministic snapshot.
- The MCP response includes identity/provenance, facts, comparable history, deterministic derived metrics, machine-readable trends, restatement status, missing/excluded metrics, and `execution_authority: NONE`.
- No raw filing date is represented as a known-at timestamp. Missing market price, forward estimates, EBITDA, or other required valuation inputs remain `NOT_AVAILABLE` with a reason. No valuation value is invented.

## Evidence discipline

Every factual numeric item passed to the tool is certified against the exact SEC accession and acceptance time. Items after `analysis_cutoff`, with a CIK/accession mismatch, missing acceptance metadata, invalid unit/context, or failed certification are excluded. The snapshot continues to preserve fiscal period, period end, filing metadata, acceptance/known time, accession, form, source URI/hash, provider, and PIT state.

`company_facts` remains read-only and always reports `execution_authority: NONE`; no broker, account credential, or order capability was added.

## Verification

- Focused SEC regression: `10 passed` (`test_fundamentals`, `test_sec_filing_metadata`, `test_sec_ticker_resolution`).
- Ruff: pass.
- Pyright: `0 errors, 0 warnings`.
- Full-suite collection: `445 tests collected`.
- A full-suite execution command could not be observed to completion in this host: the execution helper ended the process at the sandbox ACL boundary without returning a pytest result. This is recorded as an environment verification limitation, not a test pass.

## Real Astra host attempt

A fresh `codex exec` used `gpt-6-astra`, reasoning effort `high`, Codex `0.154.0`, read-only sandbox, and requested `company_facts` for GOOGL, NVDA, and META at `2026-09-11T00:00:00+00:00`.

Actual host evidence:

- the host selected `model: gpt-6-astra`, `reasoning effort: high`;
- Skill file read failed with `helper_unknown_error: apply deny-read ACLs`;
- MCP discovery returned `unknown MCP server 'meridian_alpha'` for resource queries;
- calls to `meridian-alpha/company_facts` were started but no tool result was returned before the host process ended.

Therefore no claim is made that Astra completed research or retrieved live GOOGL/NVDA/META facts. The blocker is host MCP/ACL discovery, not a fallback to fabricated data.

## Remaining acceptance work

1. Repair fresh-host ACL/MCP discovery so `meridian-alpha/company_facts` produces actual tool results.
2. Rerun the three requested Astra scenarios and record citations, acceptance timestamps, unknowns, contradictions, and `execution_authority: NONE`.
3. Rerun the full pytest suite in a host whose test process is allowed to complete.
4. Stage only the scoped Phase 2 hunks after reconciling this intentionally dirty worktree; no unrelated user modifications were staged or discarded.
