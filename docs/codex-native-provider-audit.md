# Codex-native research provider audit

Date: 2026-09-10

## Scope and conclusion

Meridian's current canonical daily and Schwab-Paper workflows use a direct
DeepSeek HTTP call in `src/meridian/research_stage.py`. The deterministic
decision, risk, reconciliation, order-planning, manual-authority and paper
execution layers do not depend on the provider implementation and can remain
unchanged. The smallest safe migration is therefore to retain the existing
`DailyResearchInput`, `DailyResearchOutput`, `ResearchDecisionContext` and
`ResearchStageResult` contracts while replacing the provider boundary.

The production replacement must be a local `codex exec` subprocess using the
Codex CLI's saved ChatGPT-managed authentication. It must not use an OpenAI or
DeepSeek SDK, API key, HTTP endpoint, OAuth implementation, or authentication
cache access.

## Current canonical call chain

1. `MeridianApplicationService._daily` loads `models.research` from
   `policies/models.yaml` and builds a bounded `DailyResearchInput` from the
   selected public quote observations.
2. `CanonicalResearchStage.run` validates input freshness, provider/model
   agreement, live/fixture/replay mode, cutoff age and the research universe
   budget.
3. The stage requires `provider == "deepseek"` and reads
   `DEEPSEEK_API_KEY`.
4. It creates an OpenAI-compatible chat-completions body and calls
   `https://api.deepseek.com/chat/completions` through
   `_default_deepseek_http_post`.
5. It extracts `choices[0].message.content`, performs free-text JSON
   extraction, validates `DailyResearchOutput`, checks exact symbol coverage
   and citation references, and emits a `ResearchDecisionContext` with
   `authority = ADVISORY_ONLY`.
6. `DailyClosureService.run` records that context but derives portfolio
   quantities, prices and gates solely from deterministic policies and market
   data.
7. Readiness maps research `AVAILABLE` to a degraded/advisory readiness state;
   research never issues manual authority or certifies public execution quotes.
8. `paper_run` requires canonical research status `AVAILABLE`; otherwise it
   adds `PAPER_EXECUTION_BLOCKED_RESEARCH_<STATUS>` and returns
   `PAPER_BLOCKED` without fills.

## INVALID_RESPONSE / NO_ACTION / PAPER_BLOCKED trace

- DeepSeek envelope, free-text JSON extraction, schema, citation, temporal or
  secret-echo failures become `INVALID_RESPONSE` and use error codes such as
  `RESEARCH_INVALID_RESPONSE`, `RESEARCH_RESPONSE_REJECTED` or
  `RESEARCH_SCHEMA_INVALID`.
- `DailyClosureService` independently produces `NO_ACTION` when deterministic
  planning has no orders and no violations. It does not treat model prose as
  allocation input.
- `paper_run` blocks whenever research is not `AVAILABLE`, even if the
  deterministic decision is `NO_ACTION`. This is the correct fail-closed
  boundary and must remain.
- `PAPER_BLOCKED` may also be caused by market session, market data,
  canonical-runtime, or deterministic-decision gates. Provider migration must
  not alter those meanings.

## Interfaces that remain

- `DailyResearchInput` and its bounded public-observation allowlist.
- `DailyResearchOutput` / `SymbolResearch` and their exact coverage/citation
  validation.
- `ResearchDecisionContext` and `ADVISORY_ONLY` authority.
- `ResearchStageResult` as the application/reporting handoff.
- Replay validation, research universe budgets and all freshness gates.
- `DailyClosureService`, deterministic allocation, risk, reconciliation,
  order planning, manual authority and Schwab-Paper ledger behavior.

## Implementations that must change

- Replace the canonical stage's DeepSeek credential and HTTP transport with a
  provider-neutral interface and `CodexCliProvider`.
- Invoke `codex exec` with an argument array, `--ephemeral`, explicit
  `--sandbox read-only`, `--output-schema`, `--output-last-message`, no
  `--search`, and JSON on UTF-8 stdin.
- Replace free-text JSON extraction with strict output-file JSON plus Pydantic
  validation against the same schema.
- Add explicit Codex failure classes, bounded repair retry, configurable model,
  reasoning effort and timeout, sanitized child environment, executable/auth
  diagnostics and audit hashes.
- Update runtime reports so an operator sees Codex status, validation,
  requested model/reasoning and elapsed time.
- Remove DeepSeek startup/config requirements and production settings.

## Historical and non-canonical code

- `DeepSeekGroundedResearchNormalizer` in `research.py`, the
  `live_shadow.py` DeepSeek runner, and the pinned TradingAgents adapter are
  earlier shadow/certification experiments. They are not invoked by the
  canonical daily or Schwab-Paper command.
- `scripts/gate3b*`, `scripts/gate6*`, replay fixtures, historical reports and
  adversarial-case names preserve prior acceptance evidence. They are not a
  permitted production fallback.
- These surfaces must either migrate to the Codex provider or be explicitly
  marked legacy/deprecated and made unreachable from current production
  configuration. Historical artifacts need not be rewritten.

## Configuration and dependency findings

- `policies/models.yaml` currently selects DeepSeek for canonical research and
  also contains legacy TradingAgents provider/model values.
- `ResearchSettings` contains a DeepSeek endpoint validator and legacy graph
  fields.
- runtime diagnostics currently reports whether a DeepSeek key is configured.
- the base package has no direct DeepSeek SDK dependency. The optional
  `research-tradingagents` extra transitively includes OpenAI-compatible
  packages; it is historical and must not be part of the Codex production
  path.

## Official Codex behavior used by the migration

Official OpenAI documentation confirms that `codex exec` is the
non-interactive workflow, reuses saved CLI authentication by default, accepts a
prompt plus piped stdin context, supports a read-only sandbox, writes its final
message with `--output-last-message`, and constrains the final response with
`--output-schema`.

References:

- https://developers.openai.com/codex/noninteractive
- https://developers.openai.com/codex/auth

## Migration boundary

The target flow is:

`Meridian bounded research packet -> CodexCliProvider -> local codex exec ->`
`strict DailyResearchOutput -> existing advisory decision context -> existing`
`deterministic gates`.

There is no automatic fallback. Any Codex failure produces no research output,
an actionable error code, `NO_ACTION` semantics at the research boundary, and
continued execution blocking.
