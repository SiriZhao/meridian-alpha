"""Small reusable structured `codex exec` boundary for auxiliary research agents."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from meridian.codex_provider import (
    ProcessRunner,
    _default_runner,
    discover_codex_executable,
    sanitized_child_environment,
)
from meridian.config import ResearchSettings


class CodexJsonError(RuntimeError):
    pass


class CodexJsonClient:
    def __init__(
        self,
        *,
        executable: str | None = None,
        runner: ProcessRunner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.executable = executable
        self.runner = runner or _default_runner
        self.environment = dict(environment or {})
        self._injected_runner = runner is not None

    def run(
        self,
        *,
        prompt: str,
        input_payload: Mapping[str, Any],
        output_schema: Mapping[str, Any],
        settings: ResearchSettings,
        search: bool = False,
    ) -> dict[str, Any]:
        environment_source = self.environment or None
        executable = self.executable or discover_codex_executable(environment_source)
        if executable is None and not self._injected_runner:
            raise CodexJsonError("CODEX_NOT_INSTALLED")
        model, effort, timeout = self._settings(settings)
        with tempfile.TemporaryDirectory(prefix="meridian-codex-agent-") as temp_name:
            directory = Path(temp_name)
            schema_path = directory / "output.schema.json"
            output_path = directory / "output.json"
            schema_path.write_text(json.dumps(output_schema), encoding="utf-8")
            command = [executable or "codex"]
            if search:
                command.append("--search")
            command.extend([
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
            ])
            if model is not None:
                command.extend(("--model", model))
            command.append(prompt)
            try:
                result = self.runner(
                    command,
                    json.dumps(input_payload, sort_keys=True, default=str),
                    sanitized_child_environment(environment_source),
                    directory,
                    timeout,
                )
            except TimeoutError as error:
                raise CodexJsonError("CODEX_TIMEOUT") from error
            except FileNotFoundError as error:
                raise CodexJsonError("CODEX_NOT_INSTALLED") from error
            except OSError as error:
                raise CodexJsonError("CODEX_PROCESS_ERROR") from error
            if result.returncode != 0:
                lowered = result.stderr.lower()
                code = (
                    "CODEX_AUTH_REQUIRED"
                    if any(
                        term in lowered
                        for term in (
                            "sign in required",
                            "please sign in",
                            "please login",
                            "login required",
                            "not logged in",
                            "authentication required",
                            "unauthorized",
                            "401 unauthorized",
                        )
                    )
                    else "CODEX_RATE_LIMITED"
                    if any(
                        term in lowered
                        for term in (
                            "rate limit",
                            "quota",
                            "usage limit",
                            "usage reset",
                            "purchase more credits",
                            "429",
                        )
                    )
                    else "CODEX_PROCESS_ERROR"
                )
                raise CodexJsonError(code)
            if not output_path.exists():
                raise CodexJsonError("CODEX_OUTPUT_MISSING")
            raw = output_path.read_text(encoding="utf-8")
            if not raw.strip():
                raise CodexJsonError("CODEX_EMPTY_RESPONSE")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as error:
                raise CodexJsonError("CODEX_SCHEMA_ERROR") from error
            if not isinstance(payload, dict):
                raise CodexJsonError("CODEX_SCHEMA_ERROR")
            return payload

    def _settings(self, settings: ResearchSettings) -> tuple[str | None, str, int]:
        environment = self.environment
        raw_model = environment.get("MERIDIAN_CODEX_MODEL", settings.model).strip()
        model = None if raw_model.lower() in {"", "default", "codex-default", "cli-default"} else raw_model
        effort = environment.get(
            "MERIDIAN_CODEX_REASONING_EFFORT", settings.reasoning_effort
        ).strip().lower()
        timeout = int(environment.get("MERIDIAN_CODEX_TIMEOUT_SECONDS", settings.timeout_seconds))
        if effort not in {"minimal", "low", "medium", "high", "xhigh"} or not 1 <= timeout <= 600:
            raise CodexJsonError("CODEX_CONFIG_INVALID")
        return model, effort, timeout
