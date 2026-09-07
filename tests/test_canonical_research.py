from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from test_recommendation_readiness import envelope

from meridian.application import MeridianApplicationService
from meridian.config import load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.research_stage import CanonicalResearchStage
from meridian.runtime import RuntimePaths, policy_directory


def settings():
    configured = load_policies(policy_directory()).models.research
    assert configured
    return configured.model_copy(update={"live_enabled": True, "llm_max_retries": 1})


def request():
    config = settings()
    return DailyResearchInput(parent_run_id="private-parent", analysis_cutoff=datetime.now(UTC),
        mode="LIVE", snapshot_reference="private-account", market_reference="market",
        policy_reference="policy", provider=config.provider, model=config.model,
        observations=(PublicResearchObservation(ticker="AAPL", observed_at=datetime.now(UTC)-timedelta(seconds=1),
            price=Decimal("100"), daily_return=Decimal("0.01"), reference="a"*64),),
        freshness_status="PASS", provider_provenance={"AAPL": "fixture"})


def response(reference="a"*64, thesis="Limited price-only inference"):
    return json.dumps({"choices": [{"message": {"content": json.dumps({"results": [{
        "ticker": "AAPL", "direction": "NEUTRAL", "research_conviction": "0.2",
        "thesis": thesis, "cited_evidence_ids": [reference], "claim_kind": "MODEL_INFERENCE",
        "data_limitations": ["No fundamental evidence"]}]})}}]}).encode()


@pytest.mark.parametrize(("http", "expected", "attempts"), [
    (200, "AVAILABLE", 1), (401, "AUTH_FAILED", 1), (403, "AUTH_FAILED", 1),
    (429, "RATE_LIMITED", 2), (503, "UNAVAILABLE", 2)])
def test_probe_is_actual_request(http, expected, attempts):
    calls = []
    def transport(url, headers, body, timeout):
        calls.append(body)
        assert b"private-account" not in body and b"private-parent" not in body
        assert timeout <= 60
        return http, response(), {}
    result = CanonicalResearchStage(transport=transport, credential=lambda: "test-secret", sleep=lambda _: None).run(request(), settings())
    assert result.context.status == expected
    assert result.attempts == len(calls) == attempts
    assert result.provenance == "FIXTURE"
    assert "test-secret" not in result.model_dump_json()


@pytest.mark.parametrize("raw", [b"not json", b'{}', response(reference="b"*64), response(thesis="test-secret")])
def test_invalid_and_secret_echo_rejected(raw):
    stage = CanonicalResearchStage(transport=lambda *args: (200, raw, {}), credential=lambda: "test-secret")
    result = stage.run(request(), settings())
    assert result.context.status == "INVALID_RESPONSE"
    assert result.context.output is None
    assert "test-secret" not in result.model_dump_json()


def test_timeout_and_disabled_missing_configuration():
    def timeout(*args):
        raise TimeoutError("test-secret")
    stage = CanonicalResearchStage(transport=timeout, credential=lambda: "test-secret", sleep=lambda _: None)
    result = stage.run(request(), settings())
    assert result.context.status == "TIMEOUT" and result.attempts == 2
    assert "test-secret" not in result.model_dump_json()
    assert stage.run(request(), None).context.status == "NOT_RUN"
    missing = CanonicalResearchStage(credential=lambda: None)
    assert missing.run(request(), settings()).context.status == "NOT_CONFIGURED"
    assert missing.run(request().model_copy(update={"mode": "FIXTURE"}), settings()).context.status == "BLOCKED"


def test_replay_and_input_boundaries():
    source = request()
    stage = CanonicalResearchStage(transport=lambda *args: (200, response(), {}), credential=lambda: "test-secret")
    recorded = stage.run(source, settings())
    replay = source.model_copy(update={"mode": "REPLAY"})
    assert stage.run(replay, settings(), replay=recorded).context.status == "AVAILABLE"
    assert stage.run(replay.model_copy(update={"policy_reference": "changed"}), settings(), replay=recorded).context.status == "BLOCKED"
    late = CanonicalResearchStage(clock=lambda: datetime.now(UTC)+timedelta(days=8))
    assert late.run(replay, settings(), replay=recorded).context.status == "BLOCKED"
    assert stage.run(source.model_copy(update={"freshness_status": "BLOCKED"}), settings()).attempts == 0
    with pytest.raises(ValueError, match="AFTER_CUTOFF"):
        DailyResearchInput.model_validate({**source.model_dump(), "analysis_cutoff": source.analysis_cutoff-timedelta(days=1)})


@pytest.mark.parametrize("future", [False, True])
@pytest.mark.parametrize("http", [200, 401])
def test_canonical_research_report_and_persistence(tmp_path, monkeypatch, future, http):
    import meridian.application as module
    policies = load_policies(policy_directory())
    policies = replace(policies, models=policies.models.model_copy(update={"research": settings()}))
    monkeypatch.setattr(module, "load_policies", lambda _: policies)
    calls = []
    def transport(url, headers, body, timeout):
        calls.append(body)
        facts = json.loads(json.loads(body)["messages"][1]["content"])["observations"]
        return http, response(reference=facts[0]["reference"]), {}
    stage = CanonicalResearchStage(transport=transport, credential=lambda: "test-secret")
    now = datetime.now(UTC)
    account = envelope(tmp_path / "account.json", now)
    market = tmp_path / "market.json"
    market.write_text(json.dumps({"quotes": [{"ticker": "AAPL", "timestamp": (now+timedelta(days=1) if future else now).isoformat(),
        "last": "100", "bid": "99.9", "ask": "100.1", "previous_close": "99", "volume": 1000000,
        "atr14": "2", "vwap": "100", "daily_return": "0.05", "gap_percent": "0.01", "freshness_state": "VERIFIED"}]}), encoding="utf-8")
    paths = RuntimePaths(tmp_path / "运行 home #2")
    result = MeridianApplicationService(paths, research_stage=stage).daily(account, market)
    assert result["research_status"] == ("BLOCKED" if future else "AVAILABLE" if http == 200 else "AUTH_FAILED")
    assert len(calls) == (0 if future else 1)
    assert isinstance(result["readiness"], dict)
    assert isinstance(result["manual_authority"], dict)
    assert isinstance(result["decision_context"], dict)
    assert result["readiness"]["recommendation_readiness"] == "BLOCKED"
    assert result["manual_authority"]["certificate_issued"] is False
    assert result["decision_context"]["research_status"] == result["research_status"]
    with closing(sqlite3.connect(paths.db)) as connection:
        stored = json.loads(connection.execute("SELECT payload_json FROM run_readiness").fetchone()[0])
        assert stored["research"]["context"]["status"] == result["research_status"]
        assert len(stored["gates"]) == 7
    for file in paths.home.rglob("*"):
        if file.is_file():
            assert b"test-secret" not in file.read_bytes()


def test_research_cannot_change_financial_parameters_and_latency_blocks():
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
        output = DailyResearchOutput.model_validate({"results": [{"ticker": "AAPL",
            "direction": direction, "research_conviction": "1", "thesis": "Model opinion",
            "claim_kind": "MODEL_INFERENCE", "data_limitations": ["Public only"],
            "cited_evidence_ids": ["a"*64]}]})
        context = ResearchDecisionContext(research_run_id="research-test", parent_run_id=baseline.decision.run_id,
            input_hash="a"*64, analysis_cutoff=NOW, status=ResearchProviderStatus.AVAILABLE, output=output)
        result = service.run(account(), market(), cutoff=NOW, research=context)
        assert result.decision == baseline.decision
        late = service.run(account(), market(), cutoff=NOW, research=context,
                           evaluated_at=NOW+timedelta(seconds=POLICIES.data.quote_max_age_seconds+1))
        assert late.decision.orders == ()
        with pytest.raises(ValueError, match="CONTEXT_MISMATCH"):
            service.run(account(), market(), cutoff=NOW, research=context.model_copy(update={"parent_run_id": "other"}))


def test_escaped_secret_echo_and_future_replay_receipt():
    source = request()
    raw = response(thesis="test-secret").replace(b"test-secret", b"test-\\u0073ecret")
    stage = CanonicalResearchStage(transport=lambda *args: (200, raw, {}), credential=lambda: "test-secret")
    assert stage.run(source, settings()).context.status == "INVALID_RESPONSE"
    good = CanonicalResearchStage(transport=lambda *args: (200, response(), {}), credential=lambda: "test-secret")
    recorded = good.run(source, settings())
    future = recorded.model_copy(update={"response_received_at": datetime.now(UTC)+timedelta(days=1)})
    assert good.run(source.model_copy(update={"mode": "REPLAY"}), settings(), replay=future).context.status == "BLOCKED"
