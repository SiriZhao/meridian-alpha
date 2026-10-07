"""Deterministic failures, temporal boundaries and lossless audit projections."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from meridian.application import MeridianApplicationService
from meridian.canonical_run import assert_report_projection_consistency, canonical_snapshot, mapping
from meridian.data.models import ValidationStatus
from meridian.data.retrieval_orchestrator import RetrievalOrchestrator
from meridian.forward_evidence import (
    ForwardLedger,
    ForwardOutcome,
    ForwardPrediction,
    ForwardPriceObservation,
)
from meridian.gpt_native_research import (
    GPTNativeResearchOrchestrator,
    InvocationStatus,
    ModelInvocationResult,
    PrimaryAnalystOutput,
    persist_research_trace,
)
from meridian.historical import (
    HistoricalAdjustmentStatus,
    HistoricalBar,
    HistoricalBarSeries,
    HistoricalProviderError,
)
from meridian.operational_data import (
    OperationalCache,
    OperationalQuote,
    OperationalReadiness,
    OperationalRefreshService,
)
from meridian.operational_market_snapshot import (
    OperationalMarketSnapshotService,
    ResilientHistoricalProvider,
)
from meridian.provider_resilience import FailureCategory, ProviderHealthStore, classify_failure
from meridian.quotes import (
    MarketSessionStatus,
    QuoteObservation,
    QuoteProviderMalformed,
    QuoteProviderTimeout,
)
from meridian.run_health import build_run_health
from meridian.runtime import RuntimePaths
from meridian.trading_calendar import TradingCalendarName, session_close
from tests.retrieval_helpers import NOW as RESEARCH_NOW
from tests.retrieval_helpers import SuccessProvider, evidence_for, requirement
from tests.test_canonical_projection_contract import fixture
from tests.test_gpt_native_research import outputs, run

NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)


class Provider:
    def __init__(self, name: str, response: QuoteObservation | Exception) -> None:
        self.provider_name, self.response, self.calls = name, response, 0

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def quote(provider: str = "yahoo", timestamp: datetime = NOW, price: str = "100") -> QuoteObservation:
    return QuoteObservation(canonical_asset_id="US-EQ-AAPL", canonical_symbol="AAPL", provider=provider,
        provider_symbol="AAPL", observed_at=timestamp, available_at=timestamp, retrieved_at=max(timestamp, NOW),
        last=Decimal(price), currency="USD", source="controlled-fixture")


class History:
    def __init__(self, provider: str = "history", *, stale: bool = False, fail: bool = False) -> None:
        self.provider_name, self.stale, self.fail, self.calls = provider, stale, fail, 0

    def get_series(self, symbol: str, start: date, end: date, *, as_of: datetime, live: bool = False) -> HistoricalBarSeries:
        self.calls += 1
        if self.fail:
            raise HistoricalProviderError("injected failure")
        sessions = [date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6)]
        if self.stale:
            sessions = sessions[:-1]
        bars = tuple(HistoricalBar(canonical_asset_id="US-EQ-AAPL", canonical_symbol=symbol,
            provider_symbol=symbol, session=session, calendar=TradingCalendarName.US_EQUITY, open=Decimal("99"), high=Decimal("101"),
            low=Decimal("98"), close=Decimal("100"), volume=Decimal("1000"), currency="USD", adjustment_status=HistoricalAdjustmentStatus.RAW,
            provider=self.provider_name, observed_at=session_close(session), available_at=session_close(session),
            retrieved_at=as_of, source="controlled-fixture") for session in sessions)
        return HistoricalBarSeries(canonical_asset_id="US-EQ-AAPL", canonical_symbol=symbol, provider=self.provider_name, as_of=as_of, bars=bars)


@pytest.mark.parametrize(("error", "category"), [
    (TimeoutError(), "TIMEOUT"), (QuoteProviderTimeout(), "TIMEOUT"),
    (HTTPError("https://example.test", 429, "", Message(), None), "RATE_LIMIT"),
    (HTTPError("https://example.test", 503, "", Message(), None), "HTTP_ERROR"),
    (HTTPError("https://example.test", 404, "", Message(), None), "SYMBOL_NOT_FOUND"),
    (URLError(TimeoutError()), "TIMEOUT"), (URLError("offline"), "NETWORK_FAILURE"),
    (QuoteProviderMalformed(), "INVALID_RESPONSE"), (ValueError(), "INVALID_RESPONSE"),
    (KeyError(), "SCHEMA_DRIFT"), (RuntimeError(), "UNKNOWN"),
])
def test_failure_taxonomy(error: Exception, category: str) -> None:
    assert classify_failure(error).value == category
    assert FailureCategory(category) is classify_failure(error)


@pytest.mark.parametrize(("first", "second", "lane", "category"), [
    ("timeout", "fresh", "FALLBACK", "TIMEOUT"),
    ("malformed", "fresh", "FALLBACK", "INVALID_RESPONSE"),
    ("schema", "fresh", "FALLBACK", "SCHEMA_DRIFT"),
    ("stale", "fresh", "FALLBACK", "STALE_DATA"),
    ("future", "fresh", "FALLBACK", "INVALID_RESPONSE"),
    ("timeout", "timeout", "NONE", "TIMEOUT"),
    ("fresh", "timeout", "PRIMARY", None),
    ("fresh", "stale", "PRIMARY", None),
    ("stale", "stale", "NONE", "STALE_DATA"),
    ("fresh", "fresh", "PRIMARY", None),
])
def test_failure_matrix_and_every_projection(tmp_path: Path, first: str, second: str, lane: str, category: str | None) -> None:
    def response(kind: str, provider: str) -> QuoteObservation | Exception:
        if kind == "timeout":
            return QuoteProviderTimeout()
        if kind == "malformed":
            return QuoteProviderMalformed()
        if kind == "schema":
            return AttributeError("injected schema drift")
        return quote(provider, NOW - timedelta(hours=1) if kind == "stale" else NOW + timedelta(seconds=1) if kind == "future" else NOW)
    primary, secondary = Provider("yahoo", response(first, "yahoo")), Provider("nasdaq", response(second, "nasdaq"))
    service = OperationalMarketSnapshotService(OperationalRefreshService(primary, secondary, cache=OperationalCache(tmp_path / "cache")), History())
    market = service.build(["AAPL", "AAPL"], analysis_time=NOW)
    assert primary.calls == secondary.calls == 1  # measured deduplication
    probe = market.provider_probes["AAPL"]
    assert probe["selection"] == lane
    primary_probe = mapping(probe["primary"])
    assert primary_probe["normalized_category"] == category
    assert primary_probe["latency_ms"] is not None
    assert primary_probe["selected"] == (lane == "PRIMARY")
    if lane == "FALLBACK":
        assert mapping(probe["secondary"])["fallback_reason"] == category
    payload = fixture("first_no_action")
    mapping(payload["market"])["provider_probes"] = market.provider_probes
    mapping(payload["market"])["status"] = probe["final_market_status"]
    outputs_ = MeridianApplicationService(RuntimePaths(tmp_path / "reports-runtime"))._persist_paper_report(payload)
    canonical = json.loads(Path(outputs_["paper_report_json"]).read_text(encoding="utf-8"))
    health = json.loads(Path(outputs_["run_health_json"]).read_text(encoding="utf-8"))
    markdown = Path(outputs_["paper_report_markdown"]).read_text(encoding="utf-8")
    assert_report_projection_consistency(canonical, markdown, health, payload)
    snapshot = canonical_snapshot(canonical)
    assert snapshot.market.quote_certification == "BLOCKED"
    assert snapshot.execution.broker_submission == "DISABLED"
    assert snapshot.execution.fill_count == 0 and not snapshot.execution.broker_side_effects
    assert snapshot.market.providers_used == (("history", "nasdaq") if lane == "FALLBACK" else ("history", "yahoo") if lane == "PRIMARY" else ())


def test_health_persists_recovers_and_never_routes(tmp_path: Path) -> None:
    path = tmp_path / "health.sqlite3"
    for index in range(3):
        health = ProviderHealthStore(path).record(provider="yahoo", symbol="AAPL" if index % 2 else "SPY", channel="LIVE_QUOTE", category="TIMEOUT", latency_ms=10 + index, completed_at=NOW, fallback=True)
    assert health["status"] == "UNHEALTHY"
    assert health["consecutive_failures"] == 3 and health["failure_scope"] == "MULTI_SYMBOL_OBSERVED"
    assert health["fallback_count"] == 3
    health = ProviderHealthStore(path).record(provider="yahoo", symbol="SPY", channel="LIVE_QUOTE", category=None, latency_ms=5, completed_at=NOW, fallback=False)
    assert health["consecutive_failures"] == 0 and health["recent_successes"] == 1
    assert health["routing_effect"] == "NONE_OBSERVATIONAL_ONLY"
    completed = subprocess.run([sys.executable, "-c", "from pathlib import Path; from datetime import datetime, UTC; from meridian.provider_resilience import ProviderHealthStore; import sys; h=ProviderHealthStore(Path(sys.argv[1])).record(provider='yahoo',symbol='SPY',channel='LIVE_QUOTE',category=None,latency_ms=1,completed_at=datetime.now(UTC),fallback=False); assert h['recent_failures']==3 and h['recent_successes']==2", str(path)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_conflict_does_not_poison_cache(tmp_path: Path) -> None:
    cache = OperationalCache(tmp_path)
    result = OperationalRefreshService(Provider("yahoo", quote()), Provider("nasdaq", quote("nasdaq", price="120")), cache=cache).refresh("AAPL", analysis_time=NOW)
    assert result.readiness is OperationalReadiness.OPERATIONAL_DEGRADED
    assert not cache._path("AAPL", "yahoo").exists()
    result = OperationalRefreshService(Provider("yahoo", TimeoutError()), Provider("nasdaq", TimeoutError()), cache=cache).refresh("AAPL", analysis_time=NOW)
    assert result.selected is None and result.selected_lane == "NONE"


@pytest.mark.parametrize("mode", ["corrupt", "wrong_symbol", "stale", "nan", "invalid_utf8"])
def test_cache_failure_is_not_live_data(tmp_path: Path, mode: str) -> None:
    cache = OperationalCache(tmp_path)
    cached = OperationalQuote.from_shadow_quote(quote(timestamp=NOW - timedelta(hours=1) if mode == "stale" else NOW))
    cache.store(cached)
    path = cache._path("AAPL", "yahoo")
    if mode == "invalid_utf8":
        path.write_bytes(b"\xff")
    elif mode == "corrupt":
        path.write_text("{", encoding="utf-8")
    elif mode in {"wrong_symbol", "nan"}:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["quote"]["symbol" if mode == "wrong_symbol" else "price"] = "SPY" if mode == "wrong_symbol" else "NaN"
        import hashlib
        raw["content_hash"] = hashlib.sha256(json.dumps(raw["quote"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        path.write_text(json.dumps(raw), encoding="utf-8")
    result = OperationalRefreshService(Provider("yahoo", TimeoutError()), cache=cache).refresh("AAPL", analysis_time=NOW)
    assert result.selected is None and result.selected_lane == "NONE"


@pytest.mark.parametrize(("when", "session"), [
    (datetime(2026, 10, 7, 12, tzinfo=UTC), "PRE_MARKET"),
    (datetime(2026, 10, 7, 21, tzinfo=UTC), "AFTER_HOURS"),
    (datetime(2026, 10, 7, 2, tzinfo=UTC), "CLOSED"),
    (datetime(2026, 11, 26, 16, tzinfo=UTC), "CLOSED"),
])
def test_session_context_and_quote_authority(when: datetime, session: str) -> None:
    from meridian.operational_data import FreshnessPolicy
    observation = OperationalQuote("AAPL", Decimal("100"), when, when, "yahoo", "PUBLIC_SHADOW_LAST", "USD", "UNKNOWN")
    description = FreshnessPolicy().describe(observation, as_of=when)
    assert description["session"] == session
    assert description["quote_kind"] == "PUBLIC_RESEARCH_QUOTE" and description["quote_certification_status"] == "BLOCKED"
    if session == "CLOSED":
        assert description["status"] == "INVALID_RESPONSE"


def test_declared_open_quote_outside_regular_session_is_invalid() -> None:
    when = datetime(2026, 10, 7, 12, tzinfo=UTC)
    observation = quote(timestamp=when).model_copy(update={"market_status": MarketSessionStatus.OPEN})
    result = OperationalRefreshService(Provider("yahoo", observation)).refresh("AAPL", analysis_time=NOW)
    assert result.primary.normalized_category is FailureCategory.SESSION_MISMATCH
    assert result.selected is None


def test_history_stale_primary_fallback_and_cache_measurement(tmp_path: Path) -> None:
    primary, secondary = History("yahoo", stale=True), History("nasdaq")
    provider = ResilientHistoricalProvider((primary, secondary), tmp_path)
    start, end = date(2026, 10, 1), date(2026, 10, 7)
    series = provider.get_series("AAPL", start, end, as_of=NOW)
    assert series.provider == "nasdaq"
    telemetry = provider.last_diagnostics["AAPL"]
    attempts = telemetry["attempts"]
    assert attempts[0]["normalized_category"] == "STALE_DATA" and attempts[1]["selected"]  # type: ignore[index]
    repeated = provider.get_series("AAPL", start, end, as_of=NOW)
    assert repeated.source_mode == "CACHE_RECOVERY"
    assert primary.calls == secondary.calls == 1
    # A cache obtained after the replay cutoff cannot satisfy earlier analysis.
    with pytest.raises(HistoricalProviderError):
        ResilientHistoricalProvider((History(fail=True),), tmp_path).get_series("AAPL", start, end, as_of=NOW - timedelta(minutes=1))


@pytest.mark.parametrize(("live_failure", "history_failure"), [(True, False), (False, True)])
def test_live_and_history_fail_independently(live_failure: bool, history_failure: bool) -> None:
    history = History(fail=history_failure)
    result = OperationalMarketSnapshotService(OperationalRefreshService(Provider("yahoo", TimeoutError() if live_failure else quote())), history).build(["AAPL"], analysis_time=NOW)
    assert not result.quotes and "AAPL" in result.missing_symbols
    assert history.calls == (0 if live_failure else 1)


def prediction(identifier: str = "p1") -> ForwardPrediction:
    return ForwardPrediction(prediction_id=identifier, decision_timestamp=NOW, information_cutoff=NOW,
        symbol="AAPL", price=Decimal("100"), quant_score=Decimal("0.2"), combined_research_score=Decimal("0.2"),
        model="fixture", provider="fixture", prompt_version="v1", software_version="test", horizon_days=1,
        trading_session=date(2026, 10, 7), maturity_session=date(2026, 10, 8), benchmark_price=Decimal("500"), source_status="CANONICAL_FROZEN")


@pytest.mark.parametrize("kind", ["late", "missing", "corporate_action_unknown", "adjusted", "delisted"])
def test_forward_incomplete_price_evidence_stays_pending(tmp_path: Path, kind: str) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    pred = prediction()
    ledger.append_prediction(pred)
    now = pred.maturity_at + timedelta(days=1)
    observations = {} if kind in {"missing", "delisted"} else {
        symbol: ForwardPriceObservation(price=Decimal(value), source_timestamp=now if kind == "late" else pred.maturity_at,
            received_at=now, source="fixture", corporate_action_status="UNKNOWN" if kind == "corporate_action_unknown" else "ADJUSTED_VERIFIED" if kind == "adjusted" else "NONE_VERIFIED")
        for symbol, value in (("AAPL", "110"), ("SPY", "510"))}
    outcome = ledger.ingest_prices(observed_at=now, prices={}, observations=observations)
    assert not outcome["appended"] and not ledger.outcomes
    assert ledger.evaluate(minimum_samples=1)["sample_count"] == 0
    assert outcome["policy_promotion"] == "NO_AUTOMATIC_PROMOTION"


def test_dated_late_delivery_is_valid_but_never_promotes_policy(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    pred = prediction()
    ledger.append_prediction(pred)
    now = pred.maturity_at + timedelta(days=2)
    observations = {symbol: ForwardPriceObservation(price=Decimal(value), source_timestamp=pred.maturity_at,
        received_at=now, source="fixture-session-close", corporate_action_status="NONE_VERIFIED") for symbol, value in (("AAPL", "110"), ("SPY", "510"))}
    outcome = ledger.ingest_prices(observed_at=now, prices={}, observations=observations)
    assert outcome["appended"] == ["p1"]
    assert ledger.ingest_prices(observed_at=now, prices={}, observations=observations)["appended"] == []
    summary = ForwardLedger(ledger.path).evaluate(minimum_samples=1, as_of=now)
    assert summary["evaluation_readiness"] == "EVALUATION_ELIGIBLE"
    assert summary["mean_excess_return"] == "0.08"
    assert summary["policy_promotion"] == "NO_AUTOMATIC_PROMOTION"
    assert summary["promotion_readiness"] == "NOT_ELIGIBLE_AUTOMATIC_PROMOTION_DISABLED"


def test_forward_failed_write_rolls_back_and_stale_writer_reloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    other = ForwardLedger(ledger.path)
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_write", lambda: (_ for _ in ()).throw(OSError("injected")))
        with pytest.raises(OSError):
            ledger.append_prediction(prediction())
    assert not ledger.predictions and not ledger.path.exists()
    ledger.append_prediction(prediction())
    other.append_prediction(prediction("p2"))
    assert set(ForwardLedger(ledger.path).predictions) == {"p1", "p2"}


def test_forward_conflicting_outcome_on_disk_is_detected(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    pred = prediction()
    ledger.append_prediction(pred)
    ledger.append_outcome(ForwardOutcome(prediction_id="p1", observed_at=pred.maturity_at, return_at_horizon=Decimal("0.1")))
    raw = json.loads(ledger.path.read_text(encoding="utf-8"))
    raw["outcomes"].append({**raw["outcomes"][0], "return_at_horizon": "0.9"})
    ledger.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="DUPLICATE_OUTCOME"):
        ForwardLedger(ledger.path)


@pytest.mark.parametrize("output", [None, {}, {"bad": "schema"}])
def test_empty_research_never_claims_success(output: dict[str, object] | None) -> None:
    checked, parsed = GPTNativeResearchOrchestrator._parse(ModelInvocationResult(status=InvocationStatus.SUCCESS, role="PRIMARY_ANALYST", output=output), PrimaryAnalystOutput, set())
    assert checked.status is InvocationStatus.SCHEMA_ERROR and parsed is None


def test_supported_claim_without_evidence_rejected() -> None:
    output = outputs()["PRIMARY_ANALYST"]
    output["supporting_claims"][0]["supporting_evidence_ids"] = []  # type: ignore[index]
    checked, parsed = GPTNativeResearchOrchestrator._parse(ModelInvocationResult(status=InvocationStatus.SUCCESS, role="PRIMARY_ANALYST", output=output), PrimaryAnalystOutput, {"a" * 64})
    assert parsed is None and checked.error_type == "SUPPORTED_CLAIM_WITHOUT_EVIDENCE"


@pytest.mark.parametrize("status", [InvocationStatus.SUCCESS, InvocationStatus.TIMEOUT, InvocationStatus.NOT_AVAILABLE, InvocationStatus.SCHEMA_ERROR])
def test_shared_research_projection_has_one_measured_runtime(tmp_path: Path, status: InvocationStatus) -> None:
    class SharedRuntime:
        calls = 0

        def invoke_chain(self, input_data, budget_seconds, *, model, reasoning_effort):
            self.calls += 1
            content = outputs()
            return ModelInvocationResult(status=status, role="RESEARCH_CHAIN", duration_ms=23000,
                model=model, output={"primary": content["PRIMARY_ANALYST"], "skeptic": content["SKEPTIC"], "scenarios": content["SCENARIO_ANALYSIS"], "synthesis": content["DECISION_SYNTHESIS"]} if status is InvocationStatus.SUCCESS else None)

    runtime = SharedRuntime()
    result = run(runtime)  # type: ignore[arg-type]
    assert runtime.calls == 1
    assert (result.research_state.value == "RESEARCH_READY") == (status is InvocationStatus.SUCCESS)
    assert result.authority == "ADVISORY_ONLY_NO_EXECUTION_AUTHORITY"
    trace = json.loads(persist_research_trace(result, RuntimePaths(tmp_path), NOW).read_text(encoding="utf-8"))
    assert all(stage["role_elapsed_ms"] is None for stage in trace["stages"])
    payload = fixture("research_executed")
    payload["research_intelligence"] = result.model_dump(mode="json")
    health = build_run_health(payload)
    roles = [stage for stage in health["stages"] if stage.get("shared_invocation_id")]  # type: ignore[union-attr]
    assert len(roles) == 4 and all(stage["elapsed_ms"] is None for stage in roles)
    assert len({stage["shared_invocation_id"] for stage in roles}) == 1
    assert all(stage["shared_invocation_wall_ms"] == 23000 for stage in roles)
    assert result.confidence.provenance.startswith("DETERMINISTIC_EVIDENCE")


def test_expired_existing_evidence_does_not_suppress_retrieval() -> None:
    item = requirement()
    provider = SuccessProvider()
    rejected = evidence_for(item, validation=ValidationStatus.REJECTED)
    RetrievalOrchestrator([provider]).retrieve([item], as_of=RESEARCH_NOW, existing_evidence=[rejected])
    assert provider.calls == 1


def test_circuit_recovers_next_run_and_retry_is_bounded() -> None:
    class Recovering(SuccessProvider):
        failing = True

        def retrieve(self, requirement, *, as_of):
            if self.failing:
                self.calls += 1
                raise TimeoutError()
            return super().retrieve(requirement, as_of=as_of)
    provider = Recovering()
    orchestrator = RetrievalOrchestrator([provider], max_retries=1, circuit_breaker_failures=1, sleeper=lambda _: None)
    package = orchestrator.retrieve([requirement()], as_of=RESEARCH_NOW)
    assert provider.calls == 2 and package.provider_results[0].failure is not None
    provider.failing = False
    package = orchestrator.retrieve([requirement()], as_of=RESEARCH_NOW)
    assert provider.calls == 3 and package.provider_results[0].evidence


def test_forward_summary_is_canonical_in_all_outputs(tmp_path: Path) -> None:
    payload = fixture("first_no_action")
    payload["forward_evidence"] = {"status": "EVALUABLE_SHADOW_ONLY", "summary": {"evaluation_readiness": "EVALUATION_ELIGIBLE", "sample_count": 20}, "authority": "SHADOW_EVIDENCE_ONLY_NO_AUTOMATIC_PROMOTION"}
    paths = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(payload)
    canonical = json.loads(Path(paths["paper_report_json"]).read_text(encoding="utf-8"))
    health = json.loads(Path(paths["run_health_json"]).read_text(encoding="utf-8"))
    assert_report_projection_consistency(canonical, Path(paths["paper_report_markdown"]).read_text(encoding="utf-8"), health, payload)
    assert health["forward_evidence"] == canonical_snapshot(canonical).forward_evidence


def test_cache_keys_are_injective_and_fresh_recovery_is_visible(tmp_path: Path) -> None:
    cache = OperationalCache(tmp_path)
    assert cache._path("AAPL-SPY", "yahoo") != cache._path("SPY", "yahoo-AAPL")
    cache.store(OperationalQuote.from_shadow_quote(quote()))
    result = OperationalRefreshService(Provider("yahoo", TimeoutError()), Provider("nasdaq", TimeoutError()), cache=cache).refresh("AAPL", analysis_time=NOW)
    assert result.selected_lane == "CACHE" and result.cache_hit
    assert result.primary.normalized_category is FailureCategory.TIMEOUT
    assert result.secondary.normalized_category is FailureCategory.TIMEOUT
    assert result.selected is not None and result.selected.provider == "yahoo"


def test_evidence_cache_detects_corruption_and_late_availability(tmp_path: Path) -> None:
    from meridian.data.retrieval_orchestrator import EvidenceCache
    cache = EvidenceCache(tmp_path, clock=lambda: RESEARCH_NOW)
    item = requirement()
    record = evidence_for(item).model_copy(update={"expires_at": RESEARCH_NOW + timedelta(hours=1)})
    cache.store(item, [record], as_of=RESEARCH_NOW)
    assert cache.load(item, as_of=RESEARCH_NOW)
    path = cache._path(item, RESEARCH_NOW)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["evidence"][0]["value"] = "999999"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert not cache.load(item, as_of=RESEARCH_NOW)


def test_future_research_memory_is_not_used(tmp_path: Path) -> None:
    from meridian.gpt_native_research import DecisionState, ResearchMemory, ResearchMemoryRecord
    memory = ResearchMemory(tmp_path)
    memory.save(ResearchMemoryRecord(symbol="AAPL", last_updated=NOW + timedelta(days=1), current_thesis="future thesis",
        confidence=0.9, direction="BULLISH", last_decision_state=DecisionState.RESEARCH_ONLY))
    assert memory.load("AAPL", as_of=NOW) is None
    assert memory.load("AAPL", as_of=NOW + timedelta(days=2)) is not None


def test_forward_lock_conflict_is_retryable_without_lost_records(tmp_path: Path) -> None:
    from meridian.forward_evidence import _hash
    from meridian.runtime_io import run_lock
    ledger = ForwardLedger(tmp_path / "forward.json")
    with run_lock(tmp_path / ".forward-locks", "injected-writer", name=_hash(str(ledger.path.resolve()))[:24]):
        with pytest.raises(OSError):
            ledger.append_prediction(prediction())
    assert not ledger.predictions and not ledger.path.exists()
    assert ledger.append_prediction(prediction()) == "APPENDED"


@pytest.mark.parametrize("provider_name", ["yahoo", "nasdaq"])
def test_real_adapter_malformed_json_is_a_typed_failure(provider_name: str) -> None:
    from meridian.quotes import NasdaqApiQuoteProvider, YahooChartQuoteProvider
    from meridian.security_master import DEFAULT_SECURITY_MASTER
    class Response:
        def read(self):
            return b"{bad-json"
    provider = (YahooChartQuoteProvider if provider_name == "yahoo" else NasdaqApiQuoteProvider)(DEFAULT_SECURITY_MASTER, opener=lambda *args, **kwargs: Response(), clock=lambda: NOW)
    with pytest.raises(QuoteProviderMalformed):
        provider.get_quote("AAPL", as_of=NOW)


def test_history_cache_corruption_and_cache_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import meridian.operational_market_snapshot as module
    provider = ResilientHistoricalProvider((History(),), tmp_path)
    start, end = date(2026, 10, 1), date(2026, 10, 7)
    provider.get_series("AAPL", start, end, as_of=NOW)
    provider._path("AAPL").write_text("{bad-cache", encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(module, "atomic_write", lambda *args: (_ for _ in ()).throw(OSError("injected")))
        series = provider.get_series("AAPL", start, end, as_of=NOW)
    assert series.bars and provider.last_diagnostics["AAPL"]["cache_status"] == "WRITE_FAILED"


def test_shadow_evaluation_does_not_sum_shared_role_wall_times() -> None:
    from meridian.gpt_native_research import FakeResearchModelRuntime
    from meridian.shadow_evaluation import ResearchQualityEvaluator
    result = run(FakeResearchModelRuntime(outputs()))
    shared = {name: stage.model_copy(update={"duration_ms": 23000, "diagnostic": {"shared_invocation": True, "shared_invocation_id": "one-call"}}) for name, stage in result.stages.items()}
    measured = ResearchQualityEvaluator().evaluate(result.model_copy(update={"stages": shared}))
    assert measured.latency_ms == 23000


@pytest.mark.parametrize("mode", ["array_drift", "timestamp_overflow", "wrong_shape"])
def test_yahoo_historical_malformed_payload_is_typed(mode: str) -> None:
    from meridian.historical import HistoricalProviderMalformed, YahooChartHistoricalProvider
    from meridian.security_master import DEFAULT_SECURITY_MASTER
    from tests.test_gate3b5_real_providers import _chart_payload, _Response
    payload = _chart_payload()
    result = payload["chart"]["result"][0]  # type: ignore[index]
    if mode == "array_drift":
        result["indicators"]["quote"][0]["close"] = [100]  # type: ignore[index]
    elif mode == "timestamp_overflow":
        result["timestamp"] = [1e300, 1e300]  # type: ignore[index]
    else:
        payload = {"chart": []}
    provider = YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER, opener=lambda *args, **kwargs: _Response(payload), clock=lambda: NOW)
    with pytest.raises(HistoricalProviderMalformed):
        provider.get_series("AAPL", date(2026, 8, 1), date(2026, 10, 7), as_of=NOW)


def test_nasdaq_incomplete_session_and_zero_volume() -> None:
    from meridian.historical import NasdaqHistoricalProvider
    from meridian.security_master import DEFAULT_SECURITY_MASTER
    from tests.test_gate3b5_real_providers import _Response
    rows = [{"date": day, "open": "100", "high": "101", "low": "99", "close": "100", "volume": 0} for day in ("10/06/2026", "10/07/2026")]
    provider = NasdaqHistoricalProvider(DEFAULT_SECURITY_MASTER, opener=lambda *args, **kwargs: _Response({"data": {"tradesTable": {"rows": rows}}}), clock=lambda: NOW)
    series = provider.get_series("AAPL", date(2026, 10, 1), date(2026, 10, 7), as_of=NOW)
    assert [bar.session for bar in series.bars] == [date(2026, 10, 6)]
    assert series.bars[0].volume == 0 and not series.bars[0].execution_price_eligible


def test_late_publication_cannot_be_supplied_as_existing_research_evidence() -> None:
    provider = SuccessProvider()
    item = requirement()
    future = evidence_for(item).model_copy(update={"available_at": RESEARCH_NOW + timedelta(seconds=1), "retrieved_at": RESEARCH_NOW + timedelta(seconds=2)})
    package = RetrievalOrchestrator([provider]).retrieve([item], as_of=RESEARCH_NOW, existing_evidence=[future])
    assert provider.calls == 1
    assert future not in package.evidence


def test_verified_forward_outcome_without_provenance_is_rejected() -> None:
    with pytest.raises(ValueError, match="PROVENANCE_REQUIRED"):
        ForwardOutcome(prediction_id="p1", observed_at=NOW, price_quality="VERIFIED_HORIZON_CLOSE", return_at_horizon=Decimal("0.1"))


def test_pre_extension_canonical_forward_fact_is_preserved() -> None:
    payload = fixture("first_no_action")
    persisted = canonical_snapshot(payload).model_dump(mode="json")
    del persisted["forward_evidence"]
    payload["canonical_state"] = persisted
    payload["forward_evidence"] = {"status": "INSUFFICIENT_FORWARD_EVIDENCE"}
    assert canonical_snapshot(payload).forward_evidence == payload["forward_evidence"]
    persisted["forward_evidence"] = {}
    assert canonical_snapshot(payload).forward_evidence == {}


def test_health_forward_drift_is_rejected(tmp_path: Path) -> None:
    payload = fixture("first_no_action")
    paths = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(payload)
    health = build_run_health(payload)
    health["forward_evidence"] = {"status": "EVALUATION_ELIGIBLE"}
    with pytest.raises(AssertionError, match="FORWARD_EVIDENCE_PROJECTION_DRIFT"):
        assert_report_projection_consistency(payload, Path(paths["paper_report_markdown"]).read_text(encoding="utf-8"), health, payload)


def test_verified_outcome_validation_is_same_after_reload(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    pred = prediction()
    ledger.append_prediction(pred)
    outcome = ForwardOutcome(prediction_id="p1", observed_at=pred.maturity_at, terminal_price=Decimal("110"),
        return_at_horizon=Decimal("0.1"), benchmark_symbol="SPY", benchmark_return=Decimal("0.02"),
        price_timestamp=pred.maturity_at, price_quality="VERIFIED_HORIZON_CLOSE")
    ledger.append_outcome(outcome)
    raw = json.loads(ledger.path.read_text(encoding="utf-8"))
    raw["outcomes"][0]["price_timestamp"] = NOW.isoformat()
    ledger.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="PROVENANCE_REQUIRED"):
        ForwardLedger(ledger.path)


def test_non_retryable_empty_response_records_actual_attempt_count() -> None:
    class Empty(SuccessProvider):
        def retrieve(self, requirement, *, as_of):
            self.calls += 1
            return ()
    provider = Empty()
    package = RetrievalOrchestrator([provider], max_retries=3).retrieve([requirement()], as_of=RESEARCH_NOW)
    failure = package.provider_results[0].failure
    assert failure is not None and failure.attempt == 1 and provider.calls == 1
    assert failure.normalized_category is FailureCategory.EMPTY_DATA


def test_forward_evaluation_does_not_look_ahead_to_outcome_delivery(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    pred = prediction()
    ledger.append_prediction(pred)
    delivery = pred.maturity_at + timedelta(days=1)
    ledger.append_outcome(ForwardOutcome(prediction_id="p1", observed_at=delivery, terminal_price=Decimal("110"),
        return_at_horizon=Decimal("0.1"), benchmark_symbol="SPY", benchmark_return=Decimal("0.02"),
        price_timestamp=pred.maturity_at, price_quality="VERIFIED_HORIZON_CLOSE"))
    earlier = ledger.evaluate(minimum_samples=1, as_of=pred.maturity_at)
    assert earlier["sample_count"] == 0 and earlier["future_outcome_count"] == 1
    assert earlier["maturity_status"] == "PENDING_OBSERVATION_TIME"
    assert ledger.evaluate(minimum_samples=1, as_of=delivery)["evaluation_readiness"] == "EVALUATION_ELIGIBLE"
