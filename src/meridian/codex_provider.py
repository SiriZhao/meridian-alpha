"""Codex CLI research provider using ChatGPT-managed local authentication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from meridian.config import ResearchSettings
from meridian.daily_research import (
    DailyResearchInput,
    DailyResearchOutput,
    ResearchFailureStatus,
    SymbolResearch,
)
from meridian.runtime_io import research_temporary_directory
from meridian.schemas import StableModel

AUTH_MODE = "CHATGPT_MANAGED_CODEX"
PROVIDER_NAME = "CODEX_CLI"
_SANITIZED_CREDENTIALS = frozenset(
    {"OPENAI_API_KEY", "CODEX_API_KEY", "DEEPSEEK_API_KEY"}
)
_MODEL_SENTINELS = frozenset({"", "default", "codex-default", "cli-default"})


class CodexError(StrEnum):
    NOT_INSTALLED = "CODEX_NOT_INSTALLED"
    AUTH_REQUIRED = "CODEX_AUTH_REQUIRED"
    TIMEOUT = "CODEX_TIMEOUT"
    RATE_LIMITED = "CODEX_RATE_LIMITED"
    PROCESS_ERROR = "CODEX_PROCESS_ERROR"
    SCHEMA_ERROR = "CODEX_SCHEMA_ERROR"
    EMPTY_RESPONSE = "CODEX_EMPTY_RESPONSE"
    OUTPUT_MISSING = "CODEX_OUTPUT_MISSING"
    CONFIG_INVALID = "CODEX_CONFIG_INVALID"


class PacketSignal(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    observed_at: AwareDatetime
    price: Decimal = Field(gt=0)
    daily_return: Decimal | None = None
    evidence_reference: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResearchPacket(StableModel):
    """Bounded, provider-neutral facts supplied to the Codex reasoning runtime."""

    schema_version: str = "codex-research-packet.v1"
    as_of: AwareDatetime
    market_session: str
    benchmark: str | None = None
    market_regime_inputs: tuple[PacketSignal, ...]
    signals: tuple[PacketSignal, ...]
    factor_scores: dict[str, str] = Field(default_factory=dict)
    candidate_assets: tuple[str, ...]
    risk_metrics: dict[str, str] = Field(default_factory=dict)
    recent_performance: dict[str, str] = Field(default_factory=dict)
    data_quality: dict[str, str]
    constraints: dict[str, str]
    existing_positions: tuple[str, ...] = ()
    proposed_changes: tuple[str, ...] = ()
    evidence_package: dict[str, Any] | None = None
    portfolio_context: dict[str, Any] | None = None

    @classmethod
    def from_daily_input(cls, request: DailyResearchInput) -> ResearchPacket:
        signals = tuple(
            PacketSignal(
                ticker=item.ticker,
                observed_at=item.observed_at,
                price=item.price,
                daily_return=item.daily_return,
                evidence_reference=item.reference,
            )
            for item in request.observations
        )
        return cls(
            as_of=(
                request.temporal_context.information_cutoff
                if request.temporal_context
                else request.analysis_cutoff
            ),
            market_session="NOT_SUPPLIED",
            market_regime_inputs=signals,
            signals=signals,
            candidate_assets=tuple(item.ticker for item in request.observations),
            data_quality={
                "freshness": request.freshness_status,
                "market_provenance": "SUPPLIED_REFERENCES_ONLY",
            },
            constraints={
                "authority": "ADVISORY_ONLY",
                "web_search": "DISABLED",
                "execution": "PROHIBITED",
                "max_assets": str(len(request.observations)),
            },
            existing_positions=tuple(
                str(item.get("ticker"))
                for item in (request.portfolio_context or {}).get("positions", [])
                if isinstance(item, dict) and item.get("ticker")
            ),
            evidence_package=request.evidence_package,
            portfolio_context=request.portfolio_context,
        )


class CodexEvidence(StableModel):
    kind: str = Field(pattern=r"^(FACT|INFERENCE|UNCERTAINTY)$")
    statement: str = Field(min_length=1, max_length=2000)
    references: tuple[str, ...] = ()


class ResearchResponse(StableModel):
    """Provider-neutral structured advisory response consumed by Meridian."""
    status: str = Field(pattern=r"^(OK|NO_ACTION|INSUFFICIENT_DATA)$")
    summary: str = Field(min_length=1, max_length=4000)
    market_regime: str = Field(min_length=1, max_length=1000)
    evidence: tuple[CodexEvidence, ...] = ()
    contradictions: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    confidence: Decimal = Field(ge=0, le=1)
    recommended_action: str = Field(
        pattern=r"^(BUY|SELL|HOLD|REBALANCE|NO_ACTION)$"
    )
    recommended_exposure_change: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=4000)
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    results: tuple[SymbolResearch, ...] = ()

    @model_validator(mode="after")
    def validate_status_contract(self) -> ResearchResponse:
        if self.status == "OK" and not self.results:
            raise ValueError("CODEX_OK_REQUIRES_RESULTS")
        if self.status != "OK" and self.results:
            raise ValueError("CODEX_NO_ACTION_RESULTS_MUST_BE_EMPTY")
        if self.status != "OK" and self.recommended_action != "NO_ACTION":
            raise ValueError("CODEX_NON_OK_ACTION_MUST_BE_NO_ACTION")
        return self


class CodexRunDiagnostics(StableModel):
    provider: str = PROVIDER_NAME
    auth_mode: str = AUTH_MODE
    model_requested: str
    reasoning_effort: str
    started_at: AwareDatetime
    elapsed_ms: int = Field(ge=0)
    exit_code: int | None = None
    schema_valid: bool = False
    research_status: str
    input_packet_hash: str
    output_hash: str | None = None
    error_class: str | None = None
    failure_status: ResearchFailureStatus | None = None


class CodexProviderResult(StableModel):
    response: ResearchResponse | None = None
    diagnostics: CodexRunDiagnostics
    attempts: int = Field(ge=0, le=2)


class ProcessResult(StableModel):
    returncode: int
    stdout: str = ""
    stderr: str = ""


ProcessRunner = Callable[
    [Sequence[str], str, Mapping[str, str], Path, int], ProcessResult
]


def sanitized_child_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ if source is None else source)
    for name in _SANITIZED_CREDENTIALS:
        environment.pop(name, None)
    environment["PYTHONUTF8"] = "1"
    return environment


def discover_codex_executable(environment: Mapping[str, str] | None = None) -> str | None:
    environment = os.environ if environment is None else environment
    search_path = environment.get("PATH")
    configured = environment.get("MERIDIAN_CODEX_EXECUTABLE")
    if configured:
        resolved = shutil.which(configured, path=search_path)
        if resolved:
            return resolved
        candidate = Path(configured)
        return str(candidate) if candidate.is_file() else None
    names = ("codex.exe", "codex") if os.name == "nt" else ("codex",)
    for name in names:
        resolved = shutil.which(name, path=search_path)
        if resolved:
            return resolved
    return None


def _asset_path(relative: str) -> Path:
    repository = Path(__file__).resolve().parents[2] / relative
    if repository.is_file():
        return repository
    packaged = Path(__file__).resolve().parent / relative
    if packaged.is_file():
        return packaged
    raise FileNotFoundError(relative)


def _default_runner(
    command: Sequence[str],
    input_text: str,
    environment: Mapping[str, str],
    cwd: Path,
    timeout_seconds: int,
) -> ProcessResult:
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        if os.name == "nt"
        else 0
    )
    process = subprocess.Popen(  # noqa: S603 - explicit trusted executable, no shell
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=dict(environment),
        shell=False,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                process.kill()
        else:
            process.kill()
        process.communicate()
        raise TimeoutError from error
    except KeyboardInterrupt:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                process.kill()
        else:
            process.kill()
        process.communicate()
        raise
    return ProcessResult(returncode=process.returncode, stdout=stdout, stderr=stderr)


class CodexCliProvider:
    """Provider-neutral structured research over one local Codex CLI process."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        runner: ProcessRunner | None = None,
        environment: Mapping[str, str] | None = None,
        prompt_path: Path | None = None,
        schema_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.environment = dict(os.environ if environment is None else environment)
        self.executable = executable
        self.runner = runner or _default_runner
        self._injected_runner = runner is not None
        self.prompt_path = prompt_path
        self.schema_path = schema_path
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _classify_process_error(stderr: str) -> CodexError:
        lowered = stderr.lower()
        if any(
            term in lowered
            for term in (
                "sign in required",
                "please sign in",
                "please login",
                "login required",
                "not logged in",
                "authentication required",
                "auth required",
                "unauthorized",
                "401 unauthorized",
            )
        ):
            return CodexError.AUTH_REQUIRED
        if any(
            term in lowered
            for term in (
                "rate limit",
                "rate_limit",
                "quota",
                "usage limit",
                "usage reset",
                "purchase more credits",
                "429",
            )
        ):
            return CodexError.RATE_LIMITED
        if any(term in lowered for term in ("error loading configuration", "invalid config", "config.toml")):
            return CodexError.CONFIG_INVALID
        return CodexError.PROCESS_ERROR

    @staticmethod
    def _settings(settings: ResearchSettings, environment: Mapping[str, str]) -> tuple[str | None, str, int]:
        model_value = environment.get("MERIDIAN_CODEX_MODEL")
        if model_value is None:
            model_value = settings.model
        model = None if model_value.strip().lower() in _MODEL_SENTINELS else model_value.strip()
        effort = environment.get("MERIDIAN_CODEX_REASONING_EFFORT", settings.reasoning_effort).strip().lower()
        if effort not in {"minimal", "low", "medium", "high", "xhigh"}:
            raise ValueError("MERIDIAN_CODEX_REASONING_EFFORT_INVALID")
        raw_timeout = environment.get("MERIDIAN_CODEX_TIMEOUT_SECONDS")
        timeout = settings.timeout_seconds if raw_timeout is None else int(raw_timeout)
        if not 1 <= timeout <= 600:
            raise ValueError("MERIDIAN_CODEX_TIMEOUT_SECONDS_INVALID")
        return model, effort, timeout

    def run(self, request: DailyResearchInput, settings: ResearchSettings) -> CodexProviderResult:
        started_at = self.clock()
        tick = time.monotonic()
        packet = ResearchPacket.from_daily_input(request)
        packet_json = packet.model_dump_json()
        # Diagnostics hash only the persistable/redacted packet. The live
        # in-memory portfolio context is intentionally excluded from hashes.
        hash_payload = packet.model_dump(
            mode="json", exclude={"portfolio_context"}
        )
        input_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        try:
            model, effort, timeout = self._settings(settings, self.environment)
            executable = self.executable or discover_codex_executable(self.environment)
            if executable is None and not self._injected_runner:
                return self._failure(
                    CodexError.NOT_INSTALLED, started_at, tick, input_hash,
                    "CLI_DEFAULT", effort, 0,
                )
            prompt_path = self.prompt_path or _asset_path("prompts/codex_research_v1.md")
            schema_path = self.schema_path or _asset_path(
                "schemas/codex_research_response.schema.json"
            )
            prompt = prompt_path.read_text(encoding="utf-8")
            json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return self._failure(
                CodexError.CONFIG_INVALID, started_at, tick, input_hash,
                "CLI_DEFAULT", "UNKNOWN", 0,
            )

        requested_model = model or "CLI_DEFAULT"
        environment = sanitized_child_environment(self.environment)
        max_attempts = min(settings.llm_retry_budget, 1) + 1
        last_error = CodexError.PROCESS_ERROR
        last_exit: int | None = None
        output_hash: str | None = None
        for attempt in range(1, max_attempts + 1):
            with research_temporary_directory() as temp_name:
                temporary = Path(temp_name)
                output_path = temporary / "research-output.json"
                command = [
                    executable or "codex",
                    "exec",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(output_path),
                    "--color",
                    "never",
                    "--config",
                    f'model_reasoning_effort="{effort}"',
                ]
                if model is not None:
                    command.extend(("--model", model))
                command.append(
                    prompt
                    if attempt == 1
                    else prompt
                    + "\n\nREPAIR RETRY: The previous final response was missing, empty, "
                    "invalid, or the process failed temporarily. Return one complete schema-valid object."
                )
                try:
                    process = self.runner(command, packet_json, environment, temporary, timeout)
                except TimeoutError:
                    return self._failure(
                        CodexError.TIMEOUT, started_at, tick, input_hash,
                        requested_model, effort, attempt,
                    )
                except FileNotFoundError:
                    return self._failure(
                        CodexError.NOT_INSTALLED, started_at, tick, input_hash,
                        requested_model, effort, attempt,
                    )
                except OSError:
                    last_error = CodexError.PROCESS_ERROR
                    if attempt < max_attempts:
                        continue
                    return self._failure(
                        last_error, started_at, tick, input_hash,
                        requested_model, effort, attempt,
                    )
                last_exit = process.returncode
                if process.returncode != 0:
                    last_error = self._classify_process_error(process.stderr[:16384])
                    if last_error is CodexError.PROCESS_ERROR and attempt < max_attempts:
                        continue
                    return self._failure(
                        last_error, started_at, tick, input_hash,
                        requested_model, effort, attempt, exit_code=last_exit,
                    )
                if not output_path.exists():
                    last_error = CodexError.OUTPUT_MISSING
                    if attempt < max_attempts:
                        continue
                    return self._failure(
                        last_error, started_at, tick, input_hash,
                        requested_model, effort, attempt, exit_code=last_exit,
                    )
                raw = output_path.read_bytes()
                if not raw.strip():
                    last_error = CodexError.EMPTY_RESPONSE
                    if attempt < max_attempts:
                        continue
                    return self._failure(
                        last_error, started_at, tick, input_hash,
                        requested_model, effort, attempt, exit_code=last_exit,
                    )
                output_hash = hashlib.sha256(raw).hexdigest()
                try:
                    response = ResearchResponse.model_validate_json(raw)
                    if response.status == "OK":
                        output = DailyResearchOutput(results=response.results)
                        output.validate_input(request)
                    supplied = {item.reference for item in request.observations}
                    if request.evidence_package:
                        raw_evidence = request.evidence_package.get("evidence", [])
                        conflicts = request.evidence_package.get("conflicts", [])
                        conflicted = {
                            str(conflict.get("requirement_key"))
                            for conflict in conflicts
                            if isinstance(conflict, dict) and conflict.get("requirement_key")
                        } if isinstance(conflicts, list) else set()
                        if isinstance(raw_evidence, list):
                            supplied.update(
                                str(item["evidence_id"])
                                for item in raw_evidence
                                if isinstance(item, dict)
                                and item.get("evidence_id")
                                and item.get("validation_status") in {"PASS", "DEGRADED"}
                                and str(item.get("requirement_key", "")) not in conflicted
                            )
                    for item in response.evidence:
                        if set(item.references) - supplied:
                            raise ValueError("CODEX_EVIDENCE_REFERENCE_INVALID")
                except (ValueError, UnicodeError):
                    last_error = CodexError.SCHEMA_ERROR
                    if attempt < max_attempts:
                        continue
                    return self._failure(
                        last_error, started_at, tick, input_hash,
                        requested_model, effort, attempt, exit_code=last_exit,
                        output_hash=output_hash,
                    )
                diagnostics = CodexRunDiagnostics(
                    model_requested=requested_model,
                    reasoning_effort=effort,
                    started_at=started_at,
                    elapsed_ms=round((time.monotonic() - tick) * 1000),
                    exit_code=process.returncode,
                    schema_valid=True,
                    research_status=response.status,
                    input_packet_hash=input_hash,
                    output_hash=output_hash,
                )
                return CodexProviderResult(
                    response=response, diagnostics=diagnostics, attempts=attempt
                )
        return self._failure(
            last_error, started_at, tick, input_hash, requested_model, effort,
            max_attempts, exit_code=last_exit, output_hash=output_hash,
        )

    @staticmethod
    def _failure(
        error: CodexError,
        started_at: datetime,
        tick: float,
        input_hash: str,
        model: str,
        effort: str,
        attempts: int,
        *,
        exit_code: int | None = None,
        output_hash: str | None = None,
    ) -> CodexProviderResult:
        failure_status = {
            CodexError.SCHEMA_ERROR: ResearchFailureStatus.SCHEMA_INVALID,
            CodexError.TIMEOUT: ResearchFailureStatus.LLM_TIMEOUT,
            CodexError.NOT_INSTALLED: ResearchFailureStatus.LLM_UNAVAILABLE,
            CodexError.AUTH_REQUIRED: ResearchFailureStatus.LLM_UNAVAILABLE,
            CodexError.PROCESS_ERROR: ResearchFailureStatus.LLM_UNAVAILABLE,
            CodexError.RATE_LIMITED: ResearchFailureStatus.LLM_UNAVAILABLE,
            CodexError.EMPTY_RESPONSE: ResearchFailureStatus.REVIEW_REQUIRED,
            CodexError.OUTPUT_MISSING: ResearchFailureStatus.REVIEW_REQUIRED,
            CodexError.CONFIG_INVALID: ResearchFailureStatus.REVIEW_REQUIRED,
        }[error]
        diagnostics = CodexRunDiagnostics(
            model_requested=model,
            reasoning_effort=effort,
            started_at=started_at,
            elapsed_ms=round((time.monotonic() - tick) * 1000),
            exit_code=exit_code,
            schema_valid=False,
            research_status="NO_ACTION",
            input_packet_hash=input_hash,
            output_hash=output_hash,
            error_class=error.value,
            failure_status=failure_status,
        )
        return CodexProviderResult(
            diagnostics=diagnostics,
            attempts=attempts,
        )


def diagnostics_dict(result: CodexProviderResult) -> dict[str, Any]:
    return result.diagnostics.model_dump(mode="json")


# Compatibility alias for early migration callers. New code uses ResearchResponse.
CodexResearchResponse = ResearchResponse
