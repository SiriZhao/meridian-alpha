from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from meridian.codex_provider import (
    AUTH_MODE,
    CodexCliProvider,
    ProcessResult,
    sanitized_child_environment,
)
from meridian.config import load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.runtime import policy_directory


def settings(*, retries: int = 1, count: int = 3):
    configured = load_policies(policy_directory()).models.research
    assert configured is not None
    budget = configured.budget.model_copy(update={"max_graph_tickers_per_run": count})
    return configured.model_copy(
        # These tests exercise the legacy CodexCliProvider contract. Keep its
        # CLI-default route independent from the production GPT-native model
        # selected in policies/models.yaml.
        update={
            "model": "codex-default",
            "live_enabled": True,
            "llm_max_retries": retries,
            "budget": budget,
        }
    )


def request(*, count: int = 1, unicode: bool = False) -> DailyResearchInput:
    now = datetime.now(UTC)
    observations = tuple(
        PublicResearchObservation(
            ticker=f"T{i}",
            observed_at=now - timedelta(seconds=1),
            price=Decimal("100.25"),
            daily_return=Decimal("0.01"),
            reference=(f"{i + 1:x}" * 64)[:64],
        )
        for i in range(count)
    )
    return DailyResearchInput(
        parent_run_id="private-parent-中文" if unicode else "private-parent",
        analysis_cutoff=now,
        mode="LIVE",
        snapshot_reference="private-snapshot-账户" if unicode else "private-snapshot",
        market_reference="market",
        policy_reference="policy",
        provider="codex_cli",
        model="codex-default",
        observations=observations,
        freshness_status="PASS",
        provider_provenance={item.ticker: "public" for item in observations},
    )


def response(source: DailyResearchInput, status: str = "OK") -> dict[str, object]:
    results = []
    if status == "OK":
        results = [
            {
                "ticker": item.ticker,
                "direction": "NEUTRAL",
                "research_conviction": 0.2,
                "thesis": "谨慎的价格证据推断",
                "risks": ["Price-only evidence"],
                "cited_evidence_ids": [item.reference],
                "claim_kind": "MODEL_INFERENCE",
                "data_limitations": ["No fundamental or news evidence"],
            }
            for item in source.observations
        ]
    return {
        "status": status,
        "summary": "Bounded evidence review.",
        "market_regime": "Uncertain from price-only evidence.",
        "evidence": [
            {
                "kind": "FACT",
                "statement": "Supplied observations were reviewed.",
                "references": [source.observations[0].reference],
            }
        ],
        "contradictions": [],
        "risks": ["Limited input breadth"],
        "data_gaps": ["Fundamentals and news not supplied"],
        "confidence": 0.2,
        "recommended_action": "HOLD" if status == "OK" else "NO_ACTION",
        "recommended_exposure_change": "MAINTAIN" if status == "OK" else "NONE",
        "rationale": "The supplied packet supports only a bounded conclusion.",
        "assumptions": [],
        "warnings": ["ADVISORY_ONLY"],
        "results": results,
    }


def fake_runner(outputs: list[object], calls: list[dict[str, Any]]):
    def run(command, input_text, environment, cwd, timeout):
        calls.append(
            {
                "command": list(command),
                "input": input_text,
                "environment": dict(environment),
                "cwd": cwd,
                "timeout": timeout,
            }
        )
        current = outputs[min(len(calls) - 1, len(outputs) - 1)]
        if isinstance(current, BaseException):
            raise current
        if isinstance(current, ProcessResult):
            return current
        output_path = Path(command[command.index("--output-last-message") + 1])
        if current != "MISSING":
            if isinstance(current, bytes):
                output_path.write_bytes(current)
            else:
                output_path.write_text(
                    json.dumps(current, ensure_ascii=False), encoding="utf-8"
                )
        return ProcessResult(returncode=0)

    return run


def provider(outputs, calls, *, environment=None):
    return CodexCliProvider(
        executable="codex-test.exe",
        runner=fake_runner(outputs, calls),
        environment=environment or {},
    )


def test_successful_structured_response_uses_safe_codex_command_and_stdin() -> None:
    source = request()
    calls: list[dict[str, Any]] = []
    result = provider([response(source)], calls).run(source, settings())
    assert result.response is not None and result.response.status == "OK"
    assert result.diagnostics.schema_valid
    assert result.diagnostics.auth_mode == AUTH_MODE
    command = calls[0]["command"]
    assert command[1:3] == ["exec", "--ephemeral"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in command and "--output-last-message" in command
    assert "--search" not in command and "--model" not in command
    assert not any("danger" in item or item == "--yolo" for item in command)
    packet = json.loads(str(calls[0]["input"]))
    assert packet["candidate_assets"] == ["T0"]
    assert "private-parent" not in str(calls[0]["input"])
    assert "private-snapshot" not in str(calls[0]["input"])


@pytest.mark.parametrize("status", ["NO_ACTION", "INSUFFICIENT_DATA"])
def test_valid_non_action_statuses_are_structured(status: str) -> None:
    source = request()
    result = provider([response(source, status)], []).run(source, settings())
    assert result.response is not None
    assert result.response.status == status
    assert result.response.recommended_action == "NO_ACTION"
    assert result.response.results == ()


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (b"not-json", "CODEX_SCHEMA_ERROR"),
        (b"", "CODEX_EMPTY_RESPONSE"),
        ("MISSING", "CODEX_OUTPUT_MISSING"),
    ],
)
def test_malformed_empty_and_missing_outputs_fail_closed_with_one_repair(
    output: object, expected: str
) -> None:
    source = request()
    result = provider([output], []).run(source, settings(retries=1))
    assert result.response is None
    assert result.diagnostics.error_class == expected
    assert result.attempts == 2


def test_executable_missing_is_explicit_and_not_retried() -> None:
    source = request()
    environment = {
        "PATH": "",
        "MERIDIAN_CODEX_EXECUTABLE": "Z:\\missing\\codex.exe",
    }
    result = CodexCliProvider(environment=environment).run(source, settings())
    assert result.diagnostics.error_class == "CODEX_NOT_INSTALLED"
    assert result.attempts == 0


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("Please login or sign in to Codex", "CODEX_AUTH_REQUIRED"),
        ("rate limit 429 quota exhausted", "CODEX_RATE_LIMITED"),
        ("Error loading configuration: invalid config.toml", "CODEX_CONFIG_INVALID"),
    ],
)
def test_non_retryable_process_errors_are_actionable(
    stderr: str, expected: str
) -> None:
    source = request()
    calls: list[dict[str, Any]] = []
    process = ProcessResult(returncode=1, stderr=stderr)
    result = provider([process], calls).run(source, settings(retries=1))
    assert result.diagnostics.error_class == expected
    assert result.attempts == len(calls) == 1


def test_usage_limit_with_plugin_warning_is_rate_limited_not_auth() -> None:
    source = request()
    calls: list[dict[str, Any]] = []
    process = ProcessResult(
        returncode=1,
        stderr=(
            "warning: plugin descriptions shortened; "
            "You've hit your usage limit. purchase more credits."
        ),
    )
    result = provider([process], calls).run(source, settings(retries=1))
    assert result.diagnostics.error_class == "CODEX_RATE_LIMITED"
    assert result.attempts == 1


def test_timeout_is_explicit_and_process_runner_owns_cleanup() -> None:
    source = request()
    result = provider([TimeoutError()], []).run(source, settings())
    assert result.diagnostics.error_class == "CODEX_TIMEOUT"
    assert result.attempts == 1


def test_temporary_process_failure_gets_one_repair_retry() -> None:
    source = request()
    calls: list[dict[str, Any]] = []
    outputs = [ProcessResult(returncode=2, stderr="temporary process failure"), response(source)]
    result = provider(outputs, calls).run(source, settings())
    assert result.response is not None
    assert result.attempts == len(calls) == 2
    assert "REPAIR RETRY" in calls[1]["command"][-1]


def test_schema_and_citation_rejection_get_one_repair_retry() -> None:
    source = request()
    invalid = response(source)
    invalid["results"][0]["cited_evidence_ids"] = ["f" * 64]  # type: ignore[index]
    result = provider([invalid], []).run(source, settings())
    assert result.response is None
    assert result.diagnostics.error_class == "CODEX_SCHEMA_ERROR"
    assert result.attempts == 2


def test_repair_retry_can_recover_from_malformed_output() -> None:
    source = request()
    result = provider([b"{", response(source)], []).run(source, settings())
    assert result.response is not None
    assert result.attempts == 2
    assert result.diagnostics.schema_valid


def test_windows_unicode_and_large_utf8_stdin() -> None:
    source = request(count=32, unicode=True)
    calls: list[dict[str, Any]] = []
    result = provider([response(source)], calls).run(source, settings(count=32))
    assert result.response is not None
    encoded = str(calls[0]["input"]).encode("utf-8")
    assert len(encoded) > 8000
    assert result.response.results[0].thesis.startswith("谨慎")


def test_child_environment_is_sanitized_and_model_overrides_are_explicit() -> None:
    source = request()
    calls: list[dict[str, Any]] = []
    environment = {
        "PATH": "safe",
        "OPENAI_API_KEY": "forbidden",
        "CODEX_API_KEY": "forbidden",
        "DEEPSEEK_API_KEY": "forbidden",
        "MERIDIAN_CODEX_MODEL": "configured-model",
        "MERIDIAN_CODEX_REASONING_EFFORT": "high",
        "MERIDIAN_CODEX_TIMEOUT_SECONDS": "45",
    }
    result = provider([response(source)], calls, environment=environment).run(
        source, settings()
    )
    child = calls[0]["environment"]
    assert all(name not in child for name in (
        "OPENAI_API_KEY", "CODEX_API_KEY", "DEEPSEEK_API_KEY"
    ))
    command = calls[0]["command"]
    assert command[command.index("--model") + 1] == "configured-model"
    assert 'model_reasoning_effort="high"' in command
    assert calls[0]["timeout"] == 45
    assert result.diagnostics.model_requested == "configured-model"


def test_sanitizer_never_mutates_parent_and_deepseek_is_not_called() -> None:
    parent = {"DEEPSEEK_API_KEY": "x", "KEEP": "yes"}
    child = sanitized_child_environment(parent)
    assert parent["DEEPSEEK_API_KEY"] == "x"
    assert "DEEPSEEK_API_KEY" not in child and child["KEEP"] == "yes"
    source = request()
    calls: list[dict[str, Any]] = []
    result = provider([response(source)], calls, environment=parent).run(
        source, settings()
    )
    assert result.response is not None
    assert "deepseek" not in " ".join(calls[0]["command"]).lower()
