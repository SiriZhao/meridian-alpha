# Meridian Codex-native provider migration report

Date: 2026-09-11

## 1. Status

Migration status: **PASS (implementation/tests)**

Final Meridian status: **PAPER_BLOCKED (honest fail-closed outcome)**

The canonical runtime now uses the local Codex CLI with ChatGPT-managed
authentication. It needs no DeepSeek, OpenAI, or Codex API key, uses no OpenAI
SDK, and has no automatic provider fallback. The new preparation phase can
plan missing data, retrieve provenance-bearing evidence through a bounded
provider chain, derive technical features locally, and re-run research up to
three rounds before failing closed.

## 2. Original and new architecture

The old canonical stage read DEEPSEEK_API_KEY, called the DeepSeek
chat-completions HTTP endpoint, extracted free-text JSON from a provider
envelope, and collapsed several failures into INVALID_RESPONSE.

The new path is:

DailyResearchInput -> bounded ResearchPacket -> CodexCliProvider -> local
codex exec -> strict ResearchResponse -> DailyResearchOutput -> existing
ResearchDecisionContext -> existing deterministic gates.

DailyResearchInput, DailyResearchOutput, SymbolResearch,
ResearchDecisionContext, ResearchStageResult, replay, freshness, universe
budget, citation validation, deterministic sizing/risk/reconciliation/order
planning, manual authority, and paper-ledger semantics remain unchanged.
Research authority remains ADVISORY_ONLY.

## 3. Codex invocation method

CodexCliProvider discovers native codex.exe first on Windows and uses
subprocess.Popen with an argument array and shell=False. The invocation uses:

- codex exec
- --ephemeral
- --ignore-user-config and --ignore-rules
- --sandbox read-only
- --skip-git-repo-check
- --output-schema and --output-last-message
- --color never
- model_reasoning_effort config override
- optional --model only when explicitly configured

ResearchPacket JSON is UTF-8 stdin. The process runs in an empty temporary
directory. Search, workspace-write, danger-full-access, yolo, and sandbox
bypass flags are never enabled. Temporary output is cleaned after each attempt.
Ignoring user configuration also prevents a custom/API provider or unrelated
MCP configuration from altering the controlled runtime; authentication is
still reused. With no Meridian model override, Codex uses its CLI default.

## 4. Authentication design

Auth mode is always CHATGPT_MANAGED_CODEX. The child environment removes
OPENAI_API_KEY, CODEX_API_KEY, and DEEPSEEK_API_KEY. Meridian does not open,
read, copy, persist, or parse auth.json, implement OAuth or token refresh, or
call api.openai.com. The native CLI reported: Logged in using ChatGPT.

Official references:

- https://developers.openai.com/codex/noninteractive
- https://developers.openai.com/codex/auth

## 5. Research packet and prompt

ResearchPacket is a bounded allowlist with cutoff, supplied regime
observations/signals, candidate assets, optional factor/risk/performance
context, data quality, constraints, and optional position/proposed-change
slots. The final evidence package uses a bounded research view: raw OHLCV
arrays are replaced by observation-count/session metadata while deterministic
derived features remain available. A cash/equity/position-weight summary is
available only in memory to the local Codex child process; it is excluded from
request dumps, hashes, reports, replay artifacts, and persisted retrieval
audit. The packet does not send account IDs, raw snapshots, credentials,
repository contents, or arbitrary prose.

The versioned prompt is prompts/codex_research_v1.md. It requires FACT /
INFERENCE / UNCERTAINTY separation, forbids invented facts and execution
instructions, permits NO_ACTION and INSUFFICIENT_DATA, and preserves the
deterministic risk engine's final veto.

## 6. Structured schema

schemas/codex_research_response.schema.json defines status, summary, market
regime, evidence, contradictions, risks, data gaps, confidence, recommended
action/exposure change, rationale, assumptions, warnings, and per-symbol
results compatible with DailyResearchOutput.

Every object has additionalProperties=false and every property is required at
the Codex boundary. Pydantic additionally enforces bounded strings, ticker and
reference formats, numeric ranges, status/action consistency, exact symbol
coverage, and exact supplied citations. The canonical path performs no
free-text JSON extraction.

## 7. Failure and retry policy

Actionable failures are:

- CODEX_NOT_INSTALLED
- CODEX_AUTH_REQUIRED
- CODEX_TIMEOUT
- CODEX_RATE_LIMITED
- CODEX_PROCESS_ERROR
- CODEX_SCHEMA_ERROR
- CODEX_EMPTY_RESPONSE
- CODEX_OUTPUT_MISSING
- CODEX_CONFIG_INVALID

Authentication, rate limit, missing executable, and invalid configuration are
not retried. Missing, empty, schema-invalid output and temporary process
failure receive at most one repair retry. Any failure returns no response,
records NO_ACTION semantics, and remains blocked. There is no fallback.

Audit diagnostics record provider, auth mode, model, reasoning, start and
elapsed time, exit code, schema validity, research status, packet/output hashes,
and error class. Credentials and auth material are not recorded.

## 8. Windows reliability

The provider prefers native codex.exe, uses UTF-8 pipes, argument arrays,
shell=False, CREATE_NEW_PROCESS_GROUP plus CREATE_NO_WINDOW, configurable
timeout (default 180 seconds), kill-and-reap cleanup on timeout/Ctrl+C, stdin
for long JSON, and temporary paths that support spaces and Unicode.

## 9. Modified files

Core:

- src/meridian/codex_provider.py
- src/meridian/research_stage.py
- src/meridian/daily_research.py
- src/meridian/config.py
- src/meridian/runtime_diagnostics.py
- src/meridian/application.py
- src/meridian/daily_closure.py
- src/meridian/research.py
- src/meridian/live_shadow.py
- src/meridian/adapters/tradingagents/engine.py
- src/meridian/data/models.py
- src/meridian/data/retrieval_orchestrator.py
- src/meridian/data/providers/base.py
- src/meridian/data/providers/structured.py
- src/meridian/research_agents/data_gap_planner.py
- src/meridian/research_agents/preparation.py
- src/meridian/research_agents/web_research_agent.py
- src/meridian/analytics/derived_market_features.py

Configuration/assets:

- policies/models.yaml
- production.env.example
- prompts/codex_research_v1.md
- schemas/codex_research_response.schema.json
- pyproject.toml
- uv.lock

Tests/scripts/docs:

- tests/test_codex_provider.py
- tests/test_canonical_research.py
- tests/test_acceptance_failures.py
- tests/test_live_llm_transport.py
- tests/test_research_universe.py
- tests/test_tradingagents_adapter.py
- tests/test_gap_planner.py
- tests/test_retrieval_orchestrator.py
- tests/test_provider_fallback.py
- tests/test_stooq_404_fallback.py
- tests/test_source_conflict.py
- tests/test_data_quality_gate.py
- tests/test_evidence_provenance.py
- tests/test_retrieval_loop.py
- tests/test_market_closed_research_allowed.py
- tests/test_execution_still_blocked_when_closed.py
- tests/test_no_llm_fabricated_market_data.py
- tests/test_web_research_agent.py
- scripts/smoke_codex_provider.py
- README.md
- docs/daily-operator-runbook.md
- docs/codex-native-provider-audit.md
- this report

The pre-existing change to reports/gate6g-quote-preflight.json was preserved
and was not part of this migration.

## 10. Tests and real runtime

Final quality gates:

- pytest: 425 passed
- Ruff: all checks passed
- Pyright: 0 errors, 0 warnings

Latest real Codex smoke (September 11, 2026):

- status: BLOCKED (external quota)
- provider: CODEX_CLI
- auth mode: CHATGPT_MANAGED_CODEX
- model: CLI_DEFAULT
- reasoning: medium
- attempts: 1
- exit code: 1
- schema valid: false (Codex did not produce an output under quota exhaustion)
- research status: NO_ACTION
- recommended action: NO_ACTION
- elapsed: 12063 ms
- error: CODEX_RATE_LIMITED (`You've hit your usage limit`; ChatGPT CLI login itself is valid)

The first development smoke exposed unsupported schema constraint keywords.
The Codex-facing schema was reduced to its supported strict subset while
Pydantic retained the stronger local validation. Subsequent smoke runs passed.

Canonical Schwab-Paper result on September 11, 2026:

- status: PAPER_BLOCKED
- NAV/cash: 100000.0000 / 100000.0000
- positions: 0
- daily/since-inception return: 0.0000 / 0.0000
- benchmark return: -0.0055
- excess return: 0.0055
- research status/error: CODEX_RATE_LIMITED
- schema valid: false (planner could not run because Codex quota was exhausted)
- decision: NO_ACTION
- paper execution: PAPER_BLOCKED
- forward evidence: BLOCKED

Paper report:
C:/Users/YOGA Pro16/AppData/Local/MeridianAlpha/reports/2026-09-11/paper-daily-2a4dc111b24fd466967d279c/paper-daily.md

RESEARCH_INVALID_RESPONSE did not recur.

## 11. Known limitations and remaining blockers

The September 11, 2026 paper run (`daily-2a4dc111b24fd466967d279c`) is `PAPER_BLOCKED` for two independent
fail-closed reasons: the NYSE session was closed/stale for execution and the
ChatGPT-managed Codex account returned `CODEX_RATE_LIMITED` while the gap
planner was running. This is an external capacity blocker, not an
authentication defect; the CLI reported a valid ChatGPT login before enforcing
the usage limit. Its `RESEARCH_READY` blocker is now explicitly
`PAPER_EXECUTION_BLOCKED_RESEARCH_CODEX_RATE_LIMITED`, rather than a generic
planner/auth error. When quota is available, the retrieval loop proceeds
without DeepSeek fallback.

Existing non-LLM gates remain intact:

- QUOTE_READY is BLOCKED because public Yahoo observations are not certified
  execution quotes.
- SECURITY_READY is DEGRADED because operational sector metadata is not
  authoritative certification.
- manual authority remains BLOCKED.
- forward evidence reported FORWARD_EVIDENCE_INTEGRITY_OR_STORAGE_FAILED and
  grants no promotion.

Historical scripts, replay case names, and reports still mention DeepSeek for
audit continuity. They are not canonical production paths. The grounded
normalizer and default TradingAgents runtime now fail closed before network
access, and TradingAgents/OpenAI SDK dependencies were removed from the lock.

## 12. Recommended next phase

Create an ADR for a privacy-minimized expansion of ResearchPacket with
certified fundamental/event evidence, benchmark/regime features, qualitative
proposed-change context, and non-persisted position-risk summaries. Keep web
search off by default. Resolve quote certification and forward-evidence storage
separately; neither should be coupled to the Codex provider or weakened to
produce a paper fill.

