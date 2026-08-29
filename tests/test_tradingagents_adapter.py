from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import meridian.adapters.tradingagents.engine as adapter_module
from meridian.adapters.tradingagents import ResearchReplayStore, TradingAgentsResearchEngine
from meridian.config import load_policies
from meridian.research import (
    GroundedResearchResult,
    ResearchEvidencePacket,
    ResearchMode,
    ResearchStatus,
)
from meridian.schemas import EvidenceItem

ROOT = Path(__file__).parents[1]
AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def settings(live=False):
    s = load_policies(ROOT / "policies").models.research
    assert s is not None
    return s.model_copy(
        update={
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "quick_model": "deepseek-v4-flash",
            "deep_model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com",
            "live_enabled": live,
            "max_retries": 1,
            "max_parallel_tickers": 2,
        }
    )


def raw(evidence_time=AS_OF):
    return {
        "direction": "BUY",
        "conviction": "0.8",
        "fundamental_score": "0.7",
        "thesis": "structured thesis",
        "evidence": [
            {
                "source": "fixture-feed",
                "observed_at": evidence_time.isoformat(),
                "evidence_type": "fixture",
                "title": "Fixture",
            }
        ],
        "shares": 999,
        "target_weight": "0.99",
        "limit_price": "1.0",
    }


def test_missing_dependency_or_credential_is_explicit(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = TradingAgentsResearchEngine(settings(live=True)).analyze("NVDA", AS_OF, {})
    assert result.status is ResearchStatus.UNAVAILABLE
    assert result.error_code == "DEEPSEEK_API_KEY_MISSING" and result.signal is None


def test_runner_normalizes_and_ignores_execution_fields(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    result = TradingAgentsResearchEngine(settings(live=True), runner=lambda *args: raw()).analyze(
        "NVDA", AS_OF, {}
    )
    assert result.status is ResearchStatus.AVAILABLE and result.signal is not None
    assert result.signal.direction == "BULLISH" and not hasattr(result.signal, "shares")
    assert result.framework == "TradingAgentsLLMProbe"
    assert "TEST_INJECTED_CLIENT_RUNNER" in result.warnings


def test_future_evidence_is_rejected(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    result = TradingAgentsResearchEngine(
        settings(live=True), runner=lambda *args: raw(AS_OF + timedelta(seconds=1))
    ).analyze("NVDA", AS_OF, {})
    assert result.status is ResearchStatus.REJECTED_EVIDENCE and result.signal is None


def test_timeout_retries_then_explicit_timeout(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    calls = []

    def runner(*args):
        calls.append(1)
        raise TimeoutError()

    result = TradingAgentsResearchEngine(settings(live=True), runner=runner).analyze(
        "NVDA", AS_OF, {}
    )
    assert result.status is ResearchStatus.TIMEOUT and result.retry_count == 1 and len(calls) == 2


def test_batch_order_is_deterministic_and_failure_isolated(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")

    def runner(ticker, *args):
        if ticker == "MSFT":
            raise RuntimeError("provider down")
        return raw()

    results = TradingAgentsResearchEngine(settings(live=True), runner=runner).analyze_many(
        ("NVDA", "AAPL", "MSFT"), AS_OF, {}
    )
    assert (
        tuple(r.ticker for r in results) == ("AAPL", "MSFT", "NVDA")
        and results[1].status is ResearchStatus.PROVIDER_ERROR
    )


def test_replay_is_separate_and_schema_checked(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    outcome = TradingAgentsResearchEngine(settings(live=True), runner=lambda *args: raw()).analyze(
        "AAPL", AS_OF, {}
    )
    store = ResearchReplayStore(tmp_path)
    path = store.record(outcome)
    assert path.is_file()
    replay = store.load("AAPL", AS_OF)
    assert replay.mode is ResearchMode.REPLAY
    replay_engine = TradingAgentsResearchEngine(
        settings(), mode=ResearchMode.REPLAY, replay_store=store
    )
    assert replay_engine.analyze("AAPL", AS_OF, {}).status is ResearchStatus.AVAILABLE


def test_deepseek_path_does_not_require_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    result = TradingAgentsResearchEngine(settings(live=True), runner=lambda *args: raw()).analyze(
        "AAPL", AS_OF, {}
    )
    assert result.status is ResearchStatus.AVAILABLE
    assert result.provider == "deepseek" and result.model_provider == "deepseek"


def test_missing_required_structured_field_is_invalid(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    payload = raw()
    payload.pop("direction")
    result = TradingAgentsResearchEngine(settings(live=True), runner=lambda *args: payload).analyze(
        "AAPL", AS_OF, {}
    )
    assert result.status is ResearchStatus.INVALID_OUTPUT


def test_provider_errors_are_explicit_and_not_neutral(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")

    def runner(*args):
        raise RuntimeError("401 authentication failed")

    result = TradingAgentsResearchEngine(settings(live=True), runner=runner).analyze(
        "AAPL", AS_OF, {}
    )
    assert result.status is ResearchStatus.PROVIDER_ERROR
    assert result.error_code == "AUTHENTICATION_FAILURE" and result.signal is None


def test_native_provider_runner_is_not_configured_when_dependency_missing(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder")
    result = TradingAgentsResearchEngine(settings(live=True)).analyze("AAPL", AS_OF, {})
    assert result.status is ResearchStatus.UNAVAILABLE
    assert result.error_code in {
        "DEEPSEEK_API_KEY_MISSING",
        "TRADINGAGENTS_NOT_INSTALLED",
        "TRADINGAGENTS_VERSION_MISMATCH",
    }


def graph_result(rating="Hold"):
    return {
        "graph_rating": rating,
        "selected_analysts": ("market", "social", "news", "fundamentals"),
        "reports_present": ("market_report", "final_trade_decision"),
        "warnings": ("no provenance",),
    }


def test_default_live_path_selects_graph_runner(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    called = []

    def fake_graph(ticker, as_of, context, settings):
        called.append(ticker)
        return graph_result("Buy")

    monkeypatch.setattr(adapter_module, "_official_graph_runner", fake_graph)
    result = TradingAgentsResearchEngine(settings(live=True)).analyze("AAPL", AS_OF, {})
    assert called == ["AAPL"]
    assert result.status is ResearchStatus.GRAPH_SUMMARY_ONLY
    assert result.framework == "TradingAgentsGraph"
    assert result.graph_rating == "Buy"
    assert result.signal is None
    assert result.selected_analysts == ("market", "social", "news", "fundamentals")
    assert result.graph_summary is not None
    assert result.graph_summary.status is ResearchStatus.GRAPH_SUMMARY_ONLY


def test_client_only_runner_cannot_masquerade_as_full_graph(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    result = TradingAgentsResearchEngine(
        settings(live=True), runner=lambda *args: raw()
    ).analyze("AAPL", AS_OF, {})
    assert result.status is ResearchStatus.AVAILABLE
    assert result.framework == "TradingAgentsLLMProbe"
    assert "TEST_INJECTED_CLIENT_RUNNER" in result.warnings


def test_graph_failure_is_explicit(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def fail_graph(*args):
        raise RuntimeError("graph vendor failure")

    result = TradingAgentsResearchEngine(
        settings(live=True), graph_runner=fail_graph
    ).analyze("AAPL", AS_OF, {})
    assert result.status is ResearchStatus.PROVIDER_ERROR
    assert result.error_code == "PROVIDER_ERROR"
    assert result.signal is None


def test_graph_invalid_rating_is_not_research_signal(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    result = TradingAgentsResearchEngine(
        settings(live=True), graph_runner=lambda *args: graph_result("BUY")
    ).analyze("AAPL", AS_OF, {})
    assert result.status is ResearchStatus.INVALID_OUTPUT
    assert result.error_code == "INVALID_OUTPUT"
    assert result.signal is None


def test_official_graph_runner_returns_only_safe_metadata(monkeypatch):
    captured = {}

    class FakeGraph:
        def __init__(self, selected_analysts, debug, config):
            captured["selected_analysts"] = tuple(selected_analysts)
            captured["debug"] = debug
            captured["config"] = config

        def propagate(self, ticker, trade_date, asset_type):
            captured["propagate"] = (ticker, trade_date, asset_type)
            return (
                {
                    "market_report": "private prose",
                    "sentiment_report": "private prose",
                    "news_report": "private prose",
                    "fundamentals_report": "private prose",
                    "investment_plan": "private prose",
                    "trader_investment_plan": "private prose",
                    "final_trade_decision": "private prose",
                },
                "Hold",
            )

    real_import = adapter_module.importlib.import_module

    def fake_import(name):
        if name == "tradingagents.graph.trading_graph":
            return SimpleNamespace(TradingAgentsGraph=FakeGraph)
        if name == "tradingagents.default_config":
            return SimpleNamespace(
                DEFAULT_CONFIG={
                    "project_dir": "home",
                    "results_dir": "home",
                    "data_cache_dir": "home",
                    "memory_log_path": "home",
                }
            )
        return real_import(name)

    monkeypatch.setattr(adapter_module.importlib, "import_module", fake_import)
    result = adapter_module._official_graph_runner("AAPL", AS_OF, {}, settings())
    assert isinstance(result, dict)
    assert result["graph_rating"] == "Hold"
    assert result["reports_present"] == (
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    )
    assert captured["propagate"] == ("AAPL", "2026-08-28", "stock")
    assert captured["config"]["checkpoint_enabled"] is False
    assert "private prose" not in str(result)


def test_historical_live_graph_call_is_forbidden_before_runner(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    calls = []

    def graph(*args):
        calls.append(args)
        return graph_result()

    historical = settings(live=True).model_copy(update={"live_as_of_tolerance_seconds": 1})
    result = TradingAgentsResearchEngine(historical, graph_runner=graph).analyze(
        "AAPL", AS_OF, {}
    )
    assert result.status is ResearchStatus.HISTORICAL_LIVE_CALL_FORBIDDEN
    assert result.error_code == "HISTORICAL_LIVE_CALL_FORBIDDEN"
    assert result.point_in_time_status.value != "LIVE_RESEARCH_OK"
    assert not calls


def test_graph_retry_budget_is_distinct_and_zero_does_not_restart(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    calls = []

    def graph(*args):
        calls.append(1)
        raise TimeoutError("graph timeout")

    configured = settings(live=True).model_copy(
        update={"max_retries": 3, "llm_max_retries": 3, "graph_max_retries": 0}
    )
    result = TradingAgentsResearchEngine(configured, graph_runner=graph).analyze(
        "AAPL", AS_OF, {}
    )
    assert result.status is ResearchStatus.TIMEOUT
    assert result.retry_count == 0 and len(calls) == 1


def test_replay_never_invokes_live_graph(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    calls = []

    def graph(*args):
        calls.append(1)
        return graph_result()

    result = TradingAgentsResearchEngine(
        settings(), mode=ResearchMode.REPLAY, replay_store=ResearchReplayStore(tmp_path), graph_runner=graph
    ).analyze("AAPL", AS_OF, {})
    assert result.status is ResearchStatus.INVALID_OUTPUT
    assert result.error_code == "REPLAY_FIXTURE_INVALID"
    assert not calls


def test_research_budget_bounds_candidates_and_reviews_holdings():
    configured = settings().model_copy(
        update={
            "budget": {
                "max_graph_tickers_per_run": 2,
                "max_parallel_graphs": 1,
                "max_graph_age_hours": 24,
                "always_review_existing_holdings": True,
                "candidate_selection_mode": "existing_then_order",
            }
        }
    )
    engine = TradingAgentsResearchEngine(configured)
    assert engine.candidate_tickers(("NVDA", "AAPL", "MSFT"), ("NVDA",)) == ("NVDA", "AAPL")


def test_evidence_packet_citations_are_resolved():
    evidence = EvidenceItem(source="fixture", observed_at=AS_OF, evidence_type="fixture")
    packet = ResearchEvidencePacket(packet_id="p1", ticker="AAPL", as_of=AS_OF, items=(evidence,))
    result = GroundedResearchResult(
        direction="BULLISH",
        research_conviction=Decimal("0.5"),
        thesis="future normalization",
        cited_evidence_ids=(evidence.stable_id,),
    )
    assert result.validate_against(packet) is result
    invalid = result.model_copy(update={"cited_evidence_ids": ("unknown",)})
    try:
        invalid.validate_against(packet)
    except ValueError as error:
        assert "unknown cited evidence" in str(error)
    else:
        raise AssertionError("unknown evidence IDs must fail closed")
