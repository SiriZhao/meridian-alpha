# Current state audit — 2026-09-29

## Repository

- HEAD: `a8d26e5e84b748c4aae048cafafafc8560b72ba0`
- Worktree: pre-existing stabilization changes plus this audit's deadline,
  review, and test additions; no unrelated changes were removed.
- Canonical runtime: `E:\MeridianAlphaRuntime`; database schema 3; approved
  host `doctor --json`: `PASS` at 2026-09-29.

## Research timeout hierarchy

- Canonical run budget: policy `native_budget.total_seconds=180`.
- Logical role budgets: primary 16s, skeptic 10s, scenario 8s, synthesis 8s.
- Cleanup margin: 2s in production policy.
- Shared `RESEARCH_CHAIN`: one subprocess hard deadline bounded by the
  monotonic parent minus cleanup margin. Configured role limits are **not**
  independently enforced in this shared process; per-role elapsed time is
  unobservable. Trace records the cooperative effective lease as
  `min(role_configured_budget, inherited_remaining - cleanup)`, while the
  actual hard cancellation boundary is the shared subprocess. They apply as
  hard limits only when roles run as separate invocations.
- Retry: Codex provider is bounded to configured retry budget and at most one
  repair attempt; native shared chain is one subprocess, with no per-role loop.
- Route: `gpt-5.6-luna`, reasoning `low` in current policy. The 2026-09-29
  approved-host paper attempt logged one `RESEARCH_CHAIN=SUCCESS` in 80,437ms
  under the 180s bound, but failed before canonical input validation.

## Failure propagation

Timeout/schema/vendor failure remains research degraded or blocked and cannot
become a successful trade. Execution remains deterministic and broker disabled.
The latest canonical command returned `MERIDIAN_INPUT_INVALID` with no output
files, because the required sanitized HostAccountSnapshotEnvelope and market
fixture were not verified. No orders, fills, or ledger mutation were reported.

## Recent canonical evidence

- 2026-09-28 report: `BLOCKED_STALE_MARKET`, `RESEARCH=FAILED`,
  `PAPER=WAITING/PAPER_SINK_NOT_EVALUATED`, orders/fills empty, broker disabled.
- 2026-09-29 doctor: runtime/database/cache/MCP/skill checks `PASS`.
- 2026-09-29 cycle 1: `daily-d175a655ad2b84f69a2f5660`, research
  `AVAILABLE`, chain 76,788ms, market `CLOSED`, paper
  `PAPER_WAITING_FOR_MARKET`, orders/fills 0, ledger version 0.
- 2026-09-29 cycle 2: `daily-3a252959eb86b0a05e8e894a`, independent chain
  73,573ms with a different invocation id, same closed-session block, orders/
  fills 0, ledger version 0.

## Quality gate caveat

Approved-host full pytest passed: 556 passed, 0 failed, 0 skipped in 70.45s.
Ruff and Pyright pass with zero diagnostics. Restricted sandbox still cannot
clean repository basetemp directories because of WinError 5; approved-host
execution with a repository-controlled temp root is the supported validation
path.
