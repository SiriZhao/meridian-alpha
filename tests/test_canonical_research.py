from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_codex_provider import (
    fake_runner,
    request,
    response,
    settings,
)
from test_recommendation_readiness import envelope

from meridian.application import MeridianApplicationService
from meridian.codex_provider import CodexCliProvider, ProcessResult
from meridian.config import load_policies
from meridian.research_stage import CanonicalResearchStage
from meridian.runtime import RuntimePaths, policy_directory


def stage(outputs: list[object], calls: list[dict[str, Any]] | None = None):
    calls = [] if calls is None else calls
    provider = CodexCliProvider(
        executable="codex-test.exe",
        runner=fake_runner(outputs, calls),
        environment={},
    )
    return CanonicalResearchStage(provider=provider)


def test_canonical_stage_consumes_provider_neutrally() -> None:
    source = request()
    calls: list[dict[str, Any]] = []
    result = stage([response(source)], calls).run(source, settings())
    assert result.context.status == "AVAILABLE"
    assert result.context.output is not None
    assert result.provider == "CODEX_CLI"
    assert result.provenance == "FIXTURE"
    assert result.provider_diagnostics["auth_mode"] == "CHATGPT_MANAGED_CODEX"
    assert len(calls) == result.attempts == 1


@pytest.mark.parametrize(
    ("payload_status", "stage_status", "code"),
    [
        ("NO_ACTION", "NO_ACTION", "CODEX_NO_ACTION"),
        ("INSUFFICIENT_DATA", "INSUFFICIENT_DATA", "CODEX_INSUFFICIENT_DATA"),
    ],
)
def test_no_action_and_insufficient_data_remain_fail_closed(
    payload_status: str, stage_status: str, code: str
) -> None:
    source = request()
    result = stage([response(source, payload_status)]).run(source, settings())
    assert result.context.status == stage_status
    assert result.context.output is None
    assert result.error_code == code
    assert result.structured_response is not None
    assert result.structured_response["recommended_action"] == "NO_ACTION"


@pytest.mark.parametrize(
    ("process", "expected"),
    [
        (ProcessResult(returncode=1, stderr="sign in required"), "CODEX_AUTH_REQUIRED"),
        (ProcessResult(returncode=1, stderr="rate limit 429"), "CODEX_RATE_LIMITED"),
        (TimeoutError(), "CODEX_TIMEOUT"),
        (b"invalid", "CODEX_SCHEMA_ERROR"),
    ],
)
def test_provider_failures_are_preserved_by_stage(
    process: object, expected: str
) -> None:
    source = request()
    result = stage([process]).run(source, settings(retries=0))
    assert result.context.status == expected
    assert result.context.output is None
    assert result.error_code == expected


def test_replay_and_input_boundaries() -> None:
    source = request()
    canonical = stage([response(source)])
    recorded = canonical.run(source, settings())
    replay = source.model_copy(update={"mode": "REPLAY"})
    assert canonical.run(replay, settings(), replay=recorded).context.status == "AVAILABLE"
    changed = replay.model_copy(update={"policy_reference": "changed"})
    assert canonical.run(changed, settings(), replay=recorded).context.status == "BLOCKED"
    late = CanonicalResearchStage(
        provider=canonical.provider,
        clock=lambda: datetime.now(UTC) + timedelta(days=8),
    )
    assert late.run(replay, settings(), replay=recorded).context.status == "BLOCKED"
    blocked = source.model_copy(update={"freshness_status": "BLOCKED"})
    assert canonical.run(blocked, settings()).attempts == 0
    assert canonical.run(source, None).context.status == "NOT_RUN"


@pytest.mark.parametrize("future", [False, True])
def test_canonical_research_report_and_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, future: bool
) -> None:
    import meridian.application as module

    configured = settings()
    policies = load_policies(policy_directory())
    policies = replace(
        policies,
        models=policies.models.model_copy(update={"research": configured}),
    )
    monkeypatch.setattr(module, "load_policies", lambda _: policies)
    now = datetime.now(UTC)
    account = envelope(tmp_path / "account.json", now)
    market = tmp_path / "market.json"
    market.write_text(
        json.dumps(
            {
                "quotes": [
                    {
                        "ticker": "AAPL",
                        "timestamp": (
                            now + timedelta(days=1) if future else now
                        ).isoformat(),
                        "last": "100",
                        "bid": "99.9",
                        "ask": "100.1",
                        "previous_close": "99",
                        "volume": 1000000,
                        "atr14": "2",
                        "vwap": "100",
                        "daily_return": "0.05",
                        "gap_percent": "0.01",
                        "freshness_state": "VERIFIED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, Any]] = []

    def runner(command, input_text, environment, cwd, timeout):
        packet = json.loads(input_text)
        reference = packet["signals"][0]["evidence_reference"]
        source = request().model_copy(
            update={
                "observations": (
                    request().observations[0].model_copy(
                        update={"ticker": "AAPL", "reference": reference}
                    ),
                )
            }
        )
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(response(source)), encoding="utf-8")
        calls.append({"input": input_text})
        return ProcessResult(returncode=0)

    provider = CodexCliProvider(
        executable="codex-test.exe", runner=runner, environment={}
    )
    paths = RuntimePaths(tmp_path / "运行 home #2")
    result = MeridianApplicationService(
        paths, research_stage=CanonicalResearchStage(provider=provider)
    ).daily(account, market)
    assert result["research_status"] == ("BLOCKED" if future else "AVAILABLE")
    assert len(calls) == (0 if future else 1)
    readiness = result["readiness"]
    authority = result["manual_authority"]
    assert isinstance(readiness, dict) and isinstance(authority, dict)
    assert readiness["recommendation_readiness"] == "BLOCKED"
    assert authority["certificate_issued"] is False
    with closing(sqlite3.connect(paths.db)) as connection:
        stored = json.loads(
            connection.execute("SELECT payload_json FROM run_readiness").fetchone()[0]
        )
        assert stored["research"]["context"]["status"] == result["research_status"]


def test_research_cannot_change_financial_parameters_and_latency_blocks() -> None:
    from test_daily_closure import NOW, POLICIES, account, market

    from meridian.daily_closure import DailyClosureService
    from meridian.daily_research import (
        DailyResearchOutput,
        ResearchDecisionContext,
        ResearchProviderStatus,
    )

    service = DailyClosureService(POLICIES)
    baseline = service.run(account(), market(), cutoff=NOW)
    for direction in ("BULLISH", "BEARISH"):
        output = DailyResearchOutput.model_validate(
            {
                "results": [
                    {
                        "ticker": "AAPL",
                        "direction": direction,
                        "research_conviction": "1",
                        "thesis": "Model opinion",
                        "claim_kind": "MODEL_INFERENCE",
                        "data_limitations": ["Public only"],
                        "cited_evidence_ids": ["a" * 64],
                    }
                ]
            }
        )
        context = ResearchDecisionContext(
            research_run_id="research-test",
            parent_run_id=baseline.decision.run_id,
            input_hash="a" * 64,
            analysis_cutoff=NOW,
            status=ResearchProviderStatus.AVAILABLE,
            output=output,
        )
        result = service.run(account(), market(), cutoff=NOW, research=context)
        assert result.decision == baseline.decision
        late = service.run(
            account(),
            market(),
            cutoff=NOW,
            research=context,
            evaluated_at=NOW + timedelta(seconds=POLICIES.data.quote_max_age_seconds + 1),
        )
        assert late.decision.orders == ()
