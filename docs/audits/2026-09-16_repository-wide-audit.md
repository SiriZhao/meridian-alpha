# Meridian Alpha repository-wide audit — 2026-09-16

## Recovered state

- Branch: `hotfix/live-advisory-20260914`
- Recovered HEAD: `873643379cf1cd05877f0abb45a16a518badae3e`
- Remote/upstream: none configured
- Worktree at recovery: staged, unstaged, and untracked stabilization changes
- Canonical application: `MeridianApplicationService`
- Safety boundary: paper only; no broker write or automatic execution surface

The recovered HEAD contains 94 tracked `.tmp` files plus generated build output.
These files explain the repository-wide Ruff baseline failure and are approved
cleanup targets, but the deletion operation was denied by the host approval
service before any file was removed.

## BASELINE BEFORE

- pytest: 526 tests collected; execution was not trustworthy because the
  sandbox denied pytest basetemp cleanup with WinError 5 and left child
  processes holding the directory. A requested non-sandbox rerun was rejected
  by the approval service.
- Ruff: 101 findings, dominated by tracked `.tmp` helper scripts and artifacts.
- Pyright: three undefined `digest` references in `application.py`.
- compileall: PASS, 0.506 seconds.
- Doctor: Python/package/Codex/MCP checks passed; configured runtime directory,
  cache, and installed Skill state failed or drifted.

## Architecture findings

The actual production chain is CLI/PowerShell/Skill paper/MCP Host-envelope →
`MeridianApplicationService` → operational market snapshot → research →
deterministic closure/allocation/risk/reconciliation → optional paper ledger →
reports. Historical CLIs, gate scripts and TradingAgents are compatibility or
diagnostic surfaces and must not own production decisions.

Primary drift:

- Host research freshness and market freshness were coupled into
  `HOST_LLM_RESULT_STALE`.
- Host symbol/evidence validation was duplicated in the application layer.
- Top-level `PAPER_BLOCKED` hid data, research, Host, decision and risk causes.
- `.tmp` and build output were committed and included in global quality checks.
- documentation described multiple generations of the runtime without a dated
  current-state section.

## Stabilization changes

- Added canonical semantic market identity and deterministic comparison.
- Added explicit exact, bounded revalidation, and refresh-required outcomes.
- Added Host job snapshot lineage and Host result snapshot/as-of/runtime binding.
- Added idempotent duplicate acceptance and conflicting duplicate rejection.
- Reused one symbol/evidence validator.
- Added six report status dimensions derived from the existing canonical state.
- Fixed Windows target-platform absolute path evaluation and nonessential Codex
  diagnostic severity from the recovered work.
- Documented the current runtime, Host lifecycle and TradingAgents defer decision.

## Validation after changes

- Pyright (`src tests`): PASS, zero errors.
- Ruff (`src tests scripts skills`): PASS.
- compileall: PASS.
- cold import: 1.039 seconds.
- CLI help: 0.970 seconds.
- workspace runtime init: PASS; schema version 3.
- doctor: code/runtime/DB/MCP/Codex checks pass in the workspace runtime, but the
  configured cache still resolves to inaccessible `E:\MeridianAlphaRuntime`,
  and the installed Skill does not contain the updated source tree.
- canonical live acceptance: not run because the authoritative paper runtime
  and ledger are inaccessible; an alternate paper account was not initialized.

## Result

`BLOCKED_WITH_EVIDENCE`. Code and documentation stabilization is present in the
worktree, but deletion approval, non-sandbox pytest, authoritative runtime/Skill
access, Git remote configuration, commit, and push remain incomplete.
