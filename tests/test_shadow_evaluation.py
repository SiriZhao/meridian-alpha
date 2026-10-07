from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from meridian.config import ModelRoutingPolicy
from meridian.gpt_native_research import (
    CodexResearchModelRuntime,
    FakeResearchModelRuntime,
    GPTNativeResearchOrchestrator,
    InvocationStatus,
)
from meridian.runtime import RuntimePaths
from meridian.shadow_evaluation import (
    GroundingValidator,
    ShadowMode,
    ShadowResearchRunner,
)
from tests.test_gpt_native_research import NOW, outputs, request, settings


def test_shadow_record_is_non_authoritative_and_persisted(tmp_path: Path) -> None:
    runner = ShadowResearchRunner(
        RuntimePaths(tmp_path / "runtime"),
        orchestrator=None,
    )
    # Inject the deterministic fake through the runner's existing orchestrator
    # boundary; no live Codex is needed by ordinary pytest.
    from meridian.gpt_native_research import GPTNativeResearchOrchestrator

    runner.orchestrator = GPTNativeResearchOrchestrator(FakeResearchModelRuntime(outputs()))
    record = runner.run(request(), settings(), mode=ShadowMode.SHADOW_LIVE, run_id="shadow-test")
    assert record.shadow_only is True
    assert record.shadow_decision_authority == "NONE"
    assert record.orders_created == record.orders_executed == 0
    assert record.quality_metrics.evidence_grounding_rate == 1.0
    target = tmp_path / "runtime" / "reports" / NOW.date().isoformat() / "shadow-test"
    assert (target / "shadow_research.json").is_file()
    assert (tmp_path / "runtime" / "data" / "research" / "calibration_log.jsonl").is_file()


def test_hallucinated_numeric_claim_is_flagged() -> None:
    result = request()
    primary = outputs()["PRIMARY_ANALYST"]
    claims = primary["supporting_claims"]
    assert isinstance(claims, list)
    claims[0]["statement"] = "The price will be 999 without evidence."
    claims[0]["supporting_evidence_ids"] = []
    catalog = outputs()
    catalog["PRIMARY_ANALYST"] = primary
    record = ShadowResearchRunner(
        RuntimePaths(Path(".pytest_tmp") / "shadow-hallucination"),
        orchestrator=GPTNativeResearchOrchestrator(FakeResearchModelRuntime(catalog)),
    ).run(result, settings(), run_id="shadow-hallucination")
    # Ungrounded supported claims are rejected before synthesis and remain
    # auditable as sanitized counts, never as usable market facts.
    assert record.quality_metrics.hallucinated_market_fact_count == 1
    assert record.stages["PRIMARY_ANALYST"]["status"] == "SCHEMA_ERROR"


def test_role_routing_is_external_and_bounded(tmp_path: Path) -> None:
    configured = settings().model_copy(
        update={
            "models": {
                "PRIMARY_ANALYST": ModelRoutingPolicy(
                    model="profile-primary", reasoning_effort="high", timeout_seconds=2, max_attempts=1
                )
            }
        }
    )
    runner = ShadowResearchRunner(RuntimePaths(tmp_path / "runtime"))
    route = runner.route(configured)
    assert route["PRIMARY_ANALYST"]["model"] == "profile-primary"
    assert route["PRIMARY_ANALYST"]["max_attempts"] == 1


def test_grounding_validator_never_promotes_unknown_evidence() -> None:
    from meridian.gpt_native_research import ClaimStatus, ResearchClaim

    check = GroundingValidator().validate(
        [
            ResearchClaim(
                claim_id="bad",
                statement="Unsupported",
                confidence=1,
                supporting_evidence_ids=("invented",),
                status=ClaimStatus.SUPPORTED,
            )
        ],
        (),
    )[0]
    assert check.status == "UNSUPPORTED"
    assert check.invalid_evidence_ids == ("invented",)


def test_sandbox_failure_is_not_misclassified_as_auth() -> None:
    runtime = CodexResearchModelRuntime(
        executable="codex",
        runner=lambda *_: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="The selected sandbox is not permitted in this context.",
        ),
    )
    result = runtime.invoke(
        "PRIMARY_ANALYST", {}, {}, 1, model="codex-default", reasoning_effort="medium"
    )
    assert result.status is InvocationStatus.PROCESS_ERROR
    assert result.error_type == "SANDBOX"
    assert result.diagnostic["auth_indicator"] is False
    assert result.diagnostic["sandbox_indicator"] is True


def test_confirmed_auth_preflight_skips_all_shadow_stages(tmp_path: Path) -> None:
    invoked: list[str] = []
    runtime = CodexResearchModelRuntime(
        executable="codex",
        runner=lambda command, *_: invoked.append(str(command[1])) or SimpleNamespace(returncode=0, stdout="", stderr=""),
        preflight_runner=lambda *_: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Not authenticated. Please log in to continue.",
        ),
    )
    record = ShadowResearchRunner(
        RuntimePaths(tmp_path / "runtime"),
        orchestrator=GPTNativeResearchOrchestrator(runtime),
    ).run(request(), settings(), mode=ShadowMode.SHADOW_LIVE, run_id="shadow-auth-blocked")
    assert record.live_preflight is not None
    assert record.live_preflight.status == "AUTH_BLOCKED"
    assert invoked == []
    assert {stage["status"] for stage in record.stages.values()} == {"NOT_RUN_AUTH_BLOCKED"}
    assert record.gpt_shadow_confidence is None
    assert record.combined_shadow_confidence is None
    assert record.gpt_confidence_status == "NOT_AVAILABLE"
    assert record.quality_metrics.metric_applicability["grounding_rate"] == "NOT_APPLICABLE_NO_MODEL_OUTPUT"
    assert record.quality_metrics.metric_applicability["hallucination_rate"] == "NOT_APPLICABLE_NO_MODEL_OUTPUT"
    assert record.orders_created == record.orders_executed == 0
