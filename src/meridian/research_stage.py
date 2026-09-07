"""Bounded canonical advisory research, reusing Meridian's DeepSeek transport."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from uuid import uuid4

from meridian.config import ResearchSettings
from meridian.daily_research import (
    DailyResearchInput,
    DailyResearchOutput,
    ResearchDecisionContext,
    ResearchStageResult,
    validate_replay,
)
from meridian.daily_research import (
    ResearchProviderStatus as Status,
)
from meridian.research import (
    LiveLLMFailure,
    _default_deepseek_http_post,
    extract_canonical_assistant_payload,
    extract_strict_json_payload,
)

Transport = Callable[[str, Mapping[str, str], bytes, int], tuple[int, bytes, Mapping[str, str]]]


class CanonicalResearchStage:
    """Actual research response is the probe; imports/configuration never mean AVAILABLE."""

    def __init__(self, *, transport: Transport | None = None,
                 credential: Callable[[], str | None] | None = None,
                 clock: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.transport = transport or _default_deepseek_http_post
        self.provenance = "LIVE_HTTP" if transport is None else "FIXTURE"
        self.credential = credential or (lambda: os.environ.get("DEEPSEEK_API_KEY"))
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep

    def run(self, request: DailyResearchInput, settings: ResearchSettings | None,
            *, replay: ResearchStageResult | None = None) -> ResearchStageResult:
        started = self.clock()
        tick = time.monotonic()
        attempts = 0
        sent = received = None
        provenance = "NONE"

        def finish(status: Status, code: str | None = None,
                   output: DailyResearchOutput | None = None) -> ResearchStageResult:
            return ResearchStageResult(
                context=ResearchDecisionContext(research_run_id="research-" + uuid4().hex,
                    parent_run_id=request.parent_run_id, input_hash=request.input_hash,
                    analysis_cutoff=request.analysis_cutoff, status=status, output=output),
                prompt_created_at=started, started_at=started, finished_at=self.clock(),
                request_sent_at=sent, response_received_at=received,
                duration_seconds=round(time.monotonic() - tick, 4), attempts=attempts,
                provider=request.provider, model=request.model, provenance=provenance,  # type: ignore[arg-type]
                error_code=code,
                next_action="Review model inferences; certified research and manual gates remain required."
                if status is Status.AVAILABLE else "Check research configuration, fresh input evidence and provider status; no prior output is substituted.",
            )

        if request.freshness_status != "PASS" or not request.observations or not request.provider_provenance:
            return finish(Status.BLOCKED, "RESEARCH_INPUT_NOT_READY")
        if request.mode == "REPLAY":
            if replay is None:
                return finish(Status.BLOCKED, "RESEARCH_REPLAY_MISSING")
            try:
                validate_replay(request, replay, replay_time=started,
                    max_age_seconds=settings.live_as_of_tolerance_seconds if settings else 86400)
            except ValueError:
                return finish(Status.BLOCKED, "RESEARCH_REPLAY_INVALID_OR_STALE")
            provenance = "REPLAY"
            received = replay.response_received_at
            return finish(Status.AVAILABLE, output=replay.context.output)
        if settings is None or not settings.live_enabled:
            return finish(Status.NOT_RUN, "LIVE_RESEARCH_DISABLED")
        if request.provider != settings.provider or request.model != settings.model:
            return finish(Status.BLOCKED, "RESEARCH_CONFIG_MISMATCH")
        if request.provider != "deepseek":
            return finish(Status.NOT_CONFIGURED, "RESEARCH_PROVIDER_UNSUPPORTED")
        if request.mode == "FIXTURE" and self.provenance != "FIXTURE":
            return finish(Status.BLOCKED, "FIXTURE_CANNOT_CALL_LIVE_PROVIDER")
        age = (started - request.analysis_cutoff).total_seconds()
        if age < 0 or age > settings.live_as_of_tolerance_seconds:
            return finish(Status.BLOCKED, "RESEARCH_CUTOFF_INVALID_OR_STALE")
        if len(request.observations) > settings.budget.max_graph_tickers_per_run:
            return finish(Status.BLOCKED, "RESEARCH_UNIVERSE_BUDGET_EXCEEDED")
        secret = self.credential()
        if not secret:
            return finish(Status.NOT_CONFIGURED, "RESEARCH_CREDENTIAL_NOT_CONFIGURED")
        # No account ID, cash, holdings, parent run IDs, or free-form input prose
        # crosses the provider boundary. Citations refer only to public observations.
        facts = [item.model_dump(mode="json") for item in request.observations]
        body = json.dumps({"model": settings.model, "temperature": 0,
            "max_tokens": 2500, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content":
                "Return JSON matching the schema. All thesis/risk statements are MODEL_INFERENCE, not facts. "
                "Use only supplied observations; cite each symbol's reference. Do not invent prices, account facts, "
                "fills, event dates or source freshness. No quantities, target weights, limit prices or gate decisions. "
                "State missing fundamental/event evidence in data_limitations. Public inputs are uncertified. "
                + json.dumps(DailyResearchOutput.model_json_schema())},
                {"role": "user", "content": json.dumps({"cutoff": request.analysis_cutoff.isoformat(),
                    "template": request.prompt_version, "observations": facts})}]}, ensure_ascii=False).encode()
        provenance = self.provenance
        status, code = Status.FAILED, "RESEARCH_REQUEST_FAILED"
        # One request covers the bounded universe; no per-symbol serial graph or unbounded retries.
        for attempt in range(min(settings.llm_retry_budget, 2) + 1):
            attempts += 1
            sent = self.clock()
            retry = False
            try:
                http, raw, _ = self.transport("https://api.deepseek.com/chat/completions",
                    {"Authorization": "Bearer " + secret, "Content-Type": "application/json"},
                    body, min(settings.timeout_seconds, 60))
                received = self.clock()
                if http in {401, 403}:
                    return finish(Status.AUTH_FAILED, "RESEARCH_AUTH_FAILED")
                if http == 429:
                    status, code, retry = Status.RATE_LIMITED, "RESEARCH_RATE_LIMITED", True
                elif http >= 500:
                    status, code, retry = Status.UNAVAILABLE, "RESEARCH_HTTP_5XX", True
                elif http != 200:
                    return finish(Status.UNAVAILABLE, "RESEARCH_HTTP_REJECTED")
                else:
                    if len(raw) > 131072 or secret.encode() in raw:
                        return finish(Status.INVALID_RESPONSE, "RESEARCH_RESPONSE_REJECTED")
                    content = extract_canonical_assistant_payload(json.loads(raw))
                    output = DailyResearchOutput.model_validate(extract_strict_json_payload(content))
                    if secret in output.model_dump_json():
                        return finish(Status.INVALID_RESPONSE, "RESEARCH_RESPONSE_REJECTED")
                    output.validate_input(request)
                    if received < sent or received < request.analysis_cutoff:
                        return finish(Status.INVALID_RESPONSE, "RESEARCH_RESPONSE_TIME_INVALID")
                    return finish(Status.AVAILABLE, output=output)
            except TimeoutError:
                status, code, retry = Status.TIMEOUT, "RESEARCH_TIMEOUT", True
            except LiveLLMFailure as error:
                retry = error.code == "NETWORK_ERROR"
                status = Status.UNAVAILABLE if retry else Status.INVALID_RESPONSE
                code = "RESEARCH_NETWORK_ERROR" if retry else "RESEARCH_INVALID_RESPONSE"
            except (ValueError, UnicodeError, TypeError, AttributeError):
                return finish(Status.INVALID_RESPONSE, "RESEARCH_SCHEMA_INVALID")
            except OSError:
                status, code, retry = Status.UNAVAILABLE, "RESEARCH_NETWORK_ERROR", True
            if not retry or attempt >= min(settings.llm_retry_budget, 2):
                break
            self.sleep(min(2 ** attempt, 2))
        return finish(status, code)
