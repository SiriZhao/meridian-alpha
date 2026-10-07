# Meridian Financial Research V2 — Final Clean-Room Installation and Machine Acceptance

Status: **BLOCKED_WITH_EVIDENCE**

Acceptance date: 2026-09-11 (Asia/Shanghai)

## Frozen baseline

- Branch: `astra/canonical-production-workflow`
- HEAD at acceptance start: `066e09f6bba5cf38881c37fc6f0a297ab755c3ac`
- Worktree: intentionally dirty from prior rounds; unrelated changes were preserved and not discarded. Final scoped acceptance changes remain uncommitted until reviewed.
- Project Python: `3.12.10` (`.venv`)
- Codex CLI: `codex-cli 0.154.0`
- Skill canonical file count: `10`
- Skill source hash: `b0ce2f4f39378592f2499c55361234fe159847d7d22aa39cceecb6045b916b32`
- Installed Skill path: `<USER_HOME>\.codex\skills\meridian-alpha`
- Installed Skill hash: matched source during the clean-room doctor run.
- Full test collection: `449`

## Quality gates

- Full pytest: `449 passed in 62.74s` after resolving the earlier Windows test cleanup lock and updating old SEC fixtures to inject the provider-neutral resolver.
- Ruff: PASS.
- Pyright: PASS, 0 errors and 0 warnings.

## Artifact and clean-room installation

Canonical wheel built with the project packaging configuration:

- Artifact: `meridian_alpha-0.0.0-py3-none-any.whl`
- SHA256: `884b8737750d1643ffd c c5c52753fe6ecc05b3827ca785af40690d25fe02fe3b` (case-insensitive; recorded from build output as `884B8737750D1643FFDCC5C52753FE6ECC05B3827CA785AF40690D25FE02FE3B`)
- The wheel contains the full 10-file canonical Skill tree under `meridian/skills/meridian-alpha/`.
- Installed into a fresh Python 3.12.10 environment outside the source checkout: `E:\MeridianCleanRoomVenv312System`.
- Import smoke succeeded from `E:\` and resolved `meridian` from `E:\MeridianCleanRoomVenv312System\Lib\site-packages\meridian\__init__.py`.
- Runtime state used a separate path: `E:\MeridianCleanRoomRuntime2`.

## Outside-checkout runtime

Clean-room `meridian doctor --json` passed after database initialization and packaged Skill hash handling were corrected:

- Python/runtime virtual environment: PASS
- Runtime directories/writes: PASS
- SQLite/database: PASS; schema version 3, migration CURRENT
- Configuration/timezone/calendar: PASS
- Codex CLI and compatibility: PASS (`0.153.4` observed by the installed runtime; host CLI is `0.154.0`)
- Authentication mode: `CHATGPT_MANAGED_CODEX`
- Skill installation: PASS; source/installed hash matched; 10 files
- MCP registration/discovery: PASS
- Secrets diagnostics: `configured=false`
- No network accessed by doctor

The only non-PASS optional checks are informational adapter checks for TradingAgents/FinRL-X/MCP presence; they do not grant execution authority.

## Real stdio MCP acceptance

A real `mcp.client.stdio` client initialized the installed server and listed 29 tools. It successfully called:

- `runtime_status`: structured PASS response, provenance metadata, `execution_authority=NONE`.
- `quant_metrics` with an empty bar fixture: explicit `REJECTED` / `BAR_AFTER_CUTOFF_OR_EMPTY`, `execution_authority=NONE`.

The registered surface contains no broker login, submit, cancel, amend, or order-execution tool. The broader compatibility tools remain read-only and manual-only.

## Fresh Astra acceptance

A completely fresh Codex invocation was attempted from outside the checkout with:

- model: `gpt-6-astra`
- reasoning effort: `high`
- sandbox: read-only
- Codex: `0.154.0`
- prompt: `Use Meridian to research GOOGL as a long-term investment. Separate facts, inference, forecast and unknowns. Show supporting and contradicting evidence.`

Actual result: `CODEX_RATE_LIMITED` / usage limit exhausted. Codex reported: `You've hit your usage limit ... try again at 11:14 PM.` No claim is made that the fresh host discovered the Skill, invoked MCP, or completed research. No recommendation or market data was fabricated.

## Failure and reload evidence

- Historical Windows cleanup initially exposed many lingering `meridian.mcp_server` processes from prior host attempts; they were identified as the cause of `.pytest_tmp` file locks. This is a real restart/reload reliability warning.
- After terminating only Meridian MCP processes, tests were rerun with an isolated basetemp and completed successfully.
- Stale/future/missing data behavior is covered by the existing test suite and remains fail-closed.
- A fresh Astra run could not be used to validate the six requested research intents because quota exhaustion occurred before tool execution.

## Remaining blockers

1. Codex/Astra account quota exhaustion prevents required fresh-host research scenarios and restart/reconnect proof.
2. A real installed-host company research request must still be run after quota reset.
3. The dirty worktree contains many prior-round changes; only acceptance reports should be committed separately unless a deliberate integration commit is requested.

## Final assessment

Local implementation, packaging, outside-checkout runtime, database migration, Skill hash synchronization, and real stdio MCP checks pass. Production acceptance cannot be declared because the mandatory fresh GPT-6 Astra host execution was blocked by the account usage limit. Final state is therefore **BLOCKED_WITH_EVIDENCE**, not PASS or PASS_WITH_WARNINGS.
