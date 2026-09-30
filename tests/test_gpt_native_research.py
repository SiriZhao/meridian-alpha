from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from meridian.application import MeridianApplicationService
from meridian.config import ResearchBudget, ResearchSettings
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.gpt_native_research import (
    CodexResearchModelRuntime,
    DecisionState,
    ExecutionState,
    FakeResearchModelRuntime,
    GPTNativeResearchOrchestrator,
    InvocationStatus,
    ModelInvocationResult,
    NativeResearchChainOutput,
    ResearchMemory,
    ResearchState,
    persist_research_trace,
)
from meridian.runtime import RuntimePaths

NOW = datetime(2026, 9, 12, 16, tzinfo=UTC)
REFERENCE = "a" * 64


def settings() -> ResearchSettings:
    return ResearchSettings(
        provider="codex_cli",
        model="codex-default",
        timeout_seconds=30,
        max_retries=0,
        debate_rounds=0,
        max_parallel_tickers=1,
        minimum_research_coverage=Decimal("1"),
        live_enabled=True,
        native_budget=ResearchBudget(
            total_seconds=10,
            primary_seconds=3,
            skeptic_seconds=2,
            scenario_seconds=2,
            synthesis_seconds=3,
        ),
    )


def request() -> DailyResearchInput:
    return DailyResearchInput(
        parent_run_id="daily-test",
        analysis_cutoff=NOW,
        mode="FIXTURE",
        snapshot_reference="b" * 64,
        market_reference="c" * 64,
        policy_reference="d" * 64,
        provider="codex_cli",
        model="codex-default",
        observations=(
            PublicResearchObservation(
                ticker="NVDA",
                observed_at=NOW,
                price=Decimal("100"),
                daily_return=Decimal("0.02"),
                reference=REFERENCE,
            ),
        ),
        freshness_status="PASS",
        provider_provenance={"NVDA": "fixture"},
    )


def outputs(*, reduction: float = 0.1) -> dict[str, dict[str, object]]:
    return {
        "PRIMARY_ANALYST": {
            "thesis": "Momentum is positive, subject to valuation risk.",
            "direction": "BULLISH",
            "key_drivers": ["positive return"],
            "supporting_claims": [
                {
                    "claim_id": "claim-1",
                    "statement": "The supplied return is positive.",
                    "confidence": 0.7,
                    "supporting_evidence_ids": [REFERENCE],
                    "contradicting_evidence_ids": [],
                    "assumptions": [],
                    "status": "SUPPORTED",
                }
            ],
            "risks": ["valuation"],
            "unknowns": ["next earnings"],
            "confidence": 0.7,
            "time_horizon": "three months",
            "evidence_used": [REFERENCE],
        },
        "SKEPTIC": {
            "challenges": ["A single return is not a valuation assessment."],
            "contradicting_evidence": [],
            "missing_evidence": ["valuation"],
            "confidence_reduction": reduction,
            "fatal_flaw": reduction >= 0.65,
        },
        "SCENARIO_ANALYSIS": {
            "bull": {"description": "Momentum persists", "probability": 0.3, "expected_direction": "BULLISH"},
            "base": {"description": "Range bound", "probability": 0.5, "expected_direction": "NEUTRAL"},
            "bear": {"description": "Valuation compresses", "probability": 0.2, "expected_direction": "BEARISH"},
            "probability_confidence": 0.5,
        },
        "DECISION_SYNTHESIS": {
            "decision_state": "RESEARCH_ONLY",
            "direction": "BULLISH",
            "confidence": 0.6,
            "conviction": "moderate",
            "time_horizon": "three months",
            "primary_thesis": "Momentum is positive, subject to valuation risk.",
            "bull_probability": 0.3,
            "base_probability": 0.5,
            "bear_probability": 0.2,
            "key_support": [REFERENCE],
            "key_risks": ["valuation"],
            "invalidators": ["negative guidance"],
            "what_changed": ["new run"],
            "required_followup": ["review earnings"],
        },
    }


def run(runtime: FakeResearchModelRuntime, *, run_id: str | None = None):
    return GPTNativeResearchOrchestrator(runtime).run(
        request(),
        research_data_status="PASS",
        execution_data_status="BLOCKED",
        execution_state=ExecutionState.BLOCKED_MARKET_CLOSED,
        settings=settings(),
        run_id=run_id,
    )


def test_closed_market_research_ready_and_no_execution_authority() -> None:
    result = run(FakeResearchModelRuntime(outputs()))
    assert result.research_state is ResearchState.READY
    assert result.decision_state is DecisionState.RESEARCH_ONLY
    assert result.execution_state is ExecutionState.BLOCKED_MARKET_CLOSED
    assert result.authority == "ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"
    assert result.confidence.system_confidence != result.confidence.llm_self_confidence


def test_primary_timeout_degrades_without_losing_structured_evidence() -> None:
    runtime = FakeResearchModelRuntime(
        {"PRIMARY_ANALYST": ModelInvocationResult(status=InvocationStatus.TIMEOUT)}
    )
    result = run(runtime)
    assert result.research_state is ResearchState.DEGRADED
    assert result.stages["PRIMARY_ANALYST"].status is InvocationStatus.TIMEOUT
    assert len(result.evidence) == 2


def test_live_codex_runtime_uses_one_bounded_research_chain() -> None:
    class ChainRuntime(FakeResearchModelRuntime):
        def __init__(self) -> None:
            super().__init__({})
            self.chain_calls: list[tuple[int, str, str]] = []

        def invoke_chain(
            self,
            input_data,
            budget_seconds,
            *,
            model,
            reasoning_effort,
        ):
            self.chain_calls.append((budget_seconds, model, reasoning_effort))
            return ModelInvocationResult(
                status=InvocationStatus.SUCCESS,
                role="RESEARCH_CHAIN",
                model=model,
                reasoning_effort=reasoning_effort,
                duration_ms=1234,
                output={
                    "primary": outputs()["PRIMARY_ANALYST"],
                    "skeptic": outputs()["SKEPTIC"],
                    "scenarios": outputs()["SCENARIO_ANALYSIS"],
                    "synthesis": outputs()["DECISION_SYNTHESIS"],
                },
                schema_valid=True,
                diagnostic={"invocation_mode": "CODEX_EXEC_EPHEMERAL_STDIN"},
            )

    runtime = ChainRuntime()
    configured = settings().model_copy(
        update={
            "timeout_seconds": 90,
            "native_budget": ResearchBudget(
                total_seconds=90,
                primary_seconds=16,
                skeptic_seconds=10,
                scenario_seconds=8,
                synthesis_seconds=8,
            ),
        }
    )
    result = GPTNativeResearchOrchestrator(runtime).run(
        request(),
        research_data_status="PASS",
        execution_data_status="BLOCKED",
        execution_state=ExecutionState.BLOCKED_MARKET_CLOSED,
        settings=configured,
        run_id="native-shared-chain",
    )
    assert runtime.calls == []
    assert runtime.chain_calls == [(90, "codex-default", "medium")]
    assert result.research_state is ResearchState.READY
    assert result.primary is not None and result.synthesis is not None
    assert {stage.status for stage in result.stages.values()} == {
        InvocationStatus.SUCCESS
    }
    assert all(
        stage.diagnostic["shared_invocation"] is True
        for stage in result.stages.values()
    )
    assert len({stage.diagnostic["shared_invocation_id"] for stage in result.stages.values()}) == 1
    NativeResearchChainOutput.model_validate(
        {
            "primary": outputs()["PRIMARY_ANALYST"],
            "skeptic": outputs()["SKEPTIC"],
            "scenarios": outputs()["SCENARIO_ANALYSIS"],
            "synthesis": outputs()["DECISION_SYNTHESIS"],
        }
    )


def test_codex_chain_runtime_uses_one_structured_process(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def runner(command, prompt, environment, directory, budget_seconds):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "primary": outputs()["PRIMARY_ANALYST"],
                    "skeptic": outputs()["SKEPTIC"],
                    "scenarios": outputs()["SCENARIO_ANALYSIS"],
                    "synthesis": outputs()["DECISION_SYNTHESIS"],
                }
            ),
            encoding="utf-8",
        )
        calls.append(
            {
                "command": command,
                "prompt": prompt,
                "environment": environment,
                "directory": directory,
                "budget_seconds": budget_seconds,
            }
        )
        return SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="model: codex-default\n",
        )

    runtime = CodexResearchModelRuntime(
        executable="codex",
        runner=runner,
        working_directory=tmp_path,
    )
    result = runtime.invoke_chain(
        {
            "evidence": [
                {
                    "evidence_id": REFERENCE,
                    "symbol": "NVDA",
                    "structured_value": {"last": "100"},
                }
            ]
        },
        90,
        model="codex-default",
        reasoning_effort="medium",
    )
    assert result.status is InvocationStatus.SUCCESS
    assert result.schema_valid is True
    assert len(calls) == 1
    assert calls[0]["budget_seconds"] == 90
    assert '"workflow"' in str(calls[0]["prompt"])
    command = calls[0]["command"]
    assert isinstance(command, list)
    assert command.count("exec") == 1
    assert "--output-schema" in command


def test_conflicting_skeptic_is_not_silently_averaged() -> None:
    result = run(FakeResearchModelRuntime(outputs(reduction=0.8)))
    assert result.decision_state is DecisionState.CONFLICTING_EVIDENCE
    assert result.disagreement_score >= 0.65


def test_all_models_unavailable_uses_deterministic_offline_fallback() -> None:
    result = run(FakeResearchModelRuntime({}))
    assert result.research_state is ResearchState.OFFLINE
    assert result.primary is None
    assert result.decision_state is DecisionState.RESEARCH_ONLY


def test_memory_and_trace_are_auditable(tmp_path) -> None:
    paths = RuntimePaths(tmp_path / "runtime")
    memory = ResearchMemory(paths.data / "research" / "memory")
    orchestrator = GPTNativeResearchOrchestrator(FakeResearchModelRuntime(outputs()), memory=memory)
    result = orchestrator.run(
        request(),
        research_data_status="PASS",
        execution_data_status="BLOCKED",
        execution_state=ExecutionState.BLOCKED_MARKET_CLOSED,
        settings=settings(),
        run_id="daily-trace",
    )
    assert memory.load("NVDA") is not None
    trace = persist_research_trace(result, paths, NOW)
    assert trace.name == "research_trace.json"
    assert "input_evidence_ids" in trace.read_text(encoding="utf-8")


def test_shared_chain_timeout_trace_identifies_single_subprocess_boundary(tmp_path) -> None:
    started = datetime(2026, 9, 12, 16, 0, tzinfo=UTC)
    finished = datetime(2026, 9, 12, 16, 0, 30, tzinfo=UTC)

    class TimeoutChainRuntime(FakeResearchModelRuntime):
        def invoke_chain(self, input_data, budget_seconds, *, model, reasoning_effort):
            return ModelInvocationResult(
                status=InvocationStatus.TIMEOUT,
                role="RESEARCH_CHAIN",
                model=model,
                reasoning_effort=reasoning_effort,
                started_at=started,
                finished_at=finished,
                duration_ms=30_000,
                error_type="TIMEOUT",
                diagnostic={
                    "shared_invocation": True,
                    "shared_invocation_role": "RESEARCH_CHAIN",
                    "prompt_bytes": 4096,
                    "deadline_ms": budget_seconds * 1000,
                    "remaining_budget_ms": 0,
                    "timeout_source": "SUBPROCESS_DEADLINE",
                    "process_exit_state": "TERMINATED",
                    "schema_state": "NOT_RETURNED",
                },
            )

    result = GPTNativeResearchOrchestrator(TimeoutChainRuntime({})).run(
        request(),
        research_data_status="PASS",
        execution_data_status="BLOCKED",
        execution_state=ExecutionState.BLOCKED_MARKET_CLOSED,
        settings=settings().model_copy(
            update={
                "timeout_seconds": 30,
                "native_budget": ResearchBudget(
                    total_seconds=30,
                    primary_seconds=16,
                    skeptic_seconds=10,
                    scenario_seconds=2,
                    synthesis_seconds=2,
                ),
            }
        ),
        run_id="daily-timeout-trace",
    )
    trace = persist_research_trace(result, RuntimePaths(tmp_path / "runtime"), NOW)
    payload = json.loads(trace.read_text(encoding="utf-8"))
    assert {item["status"] for item in payload["stages"]} == {"TIMEOUT"}
    assert all(item["telemetry"]["timeout_source"] == "SUBPROCESS_DEADLINE" for item in payload["stages"])
    assert all(item["telemetry"]["shared_invocation"] is True for item in payload["stages"])
    assert all(item["telemetry"]["deadline_ms"] == 30_000 for item in payload["stages"])


def test_native_closed_market_report_keeps_orders_at_zero(tmp_path, monkeypatch) -> None:
    # The account remains fresh, while this scenario explicitly exercises a closed exchange.
    from meridian.market_status import market_status
    monkeypatch.setattr("meridian.application.market_status", lambda _: market_status(datetime(2026, 9, 13, 14, tzinfo=UTC)))
    now = datetime.now(UTC)
    account = tmp_path / "account.json"
    market = tmp_path / "market.json"
    account.write_text(
        json.dumps(
            {
                "snapshot_id": "native-closed-test-" + uuid4().hex,
                "source_kind": "fixture",
                "source_name": "test",
                "as_of": now.isoformat(),
                "retrieved_at": now.isoformat(),
                "coverage_status": "COMPLETE",
                "cash": "10000",
                "total_equity": "10000",
            }
        ),
        encoding="utf-8",
    )
    quotes = []
    for index, ticker in enumerate(("AAPL", "MSFT", "NVDA", "SPY"), start=1):
        price = 100 + index
        quotes.append(
            {
                "ticker": ticker,
                "timestamp": now.isoformat(),
                "last": str(price),
                "bid": str(price - 0.1),
                "ask": str(price + 0.1),
                "previous_close": str(price - 1),
                "volume": 1_000_000,
                "atr14": "2",
                "vwap": str(price),
                "daily_return": "0.01",
                "gap_percent": "0",
                "freshness_state": "VERIFIED",
            }
        )
    market.write_text(json.dumps({"quotes": quotes}), encoding="utf-8")
    result = MeridianApplicationService(RuntimePaths(tmp_path / "runtime")).daily(account, market)
    # Fixture mode must not invoke the real GPT-native runtime. Market closure
    # remains an independent deterministic execution gate.
    assert result["research_intelligence"] is None
    assert result["research_status"] == "NOT_RUN"
    assert result["status"] == "NO_ACTION"
    assert result["orders"] == []
    assert result.get("research_trace_json") is None
