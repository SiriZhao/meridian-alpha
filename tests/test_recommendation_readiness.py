from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from meridian.audit import SCHEMA_VERSION, AuditStore
from meridian.host_readiness import ReadinessStatus, RecommendationReadiness, inspect_snapshot
from meridian.operational_data import FreshnessPolicy, OperationalCache, OperationalRefreshService
from meridian.trading_calendar import session_close, session_context


def envelope(path: Path, now: datetime, **updates) -> Path:
    body = {"snapshot_id": "new-synthetic", "source_kind": "fixture", "source_name": "synthetic",
            "as_of": now.isoformat(), "retrieved_at": now.isoformat(),
            "coverage_status": "COMPLETE", "cash": "10000", "total_equity": "10000"}
    body.update(updates)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


@pytest.mark.parametrize("dimension", [
    "runtime_health", "account_snapshot_status", "account_snapshot_freshness",
    "account_provenance", "market_data_status", "market_data_freshness", "provider_provenance",
    "research_status", "research_freshness", "decision_pipeline_status", "policy_gate_status",
])
def test_unknown_never_promoted(dimension: str) -> None:
    evidence = {key: ReadinessStatus.PASS for key in RecommendationReadiness.model_fields
                if key not in {"input_mode", "quote_kind"}}
    evidence[dimension] = ReadinessStatus.UNKNOWN
    result = RecommendationReadiness.model_validate({**evidence, "input_mode": "REAL_VERIFIED"})
    assert result.recommendation_readiness is ReadinessStatus.BLOCKED
    assert f"{dimension.upper()}_UNKNOWN" in result.blockers
    with pytest.raises(ValueError):
        RecommendationReadiness(recommendation_readiness="PASS")  # type: ignore[call-arg]


def test_runtime_research_and_manual_are_distinct() -> None:
    fields = {key: ReadinessStatus.PASS for key in RecommendationReadiness.model_fields
              if key not in {"input_mode", "quote_kind"}}
    fields["quote_certification_status"] = ReadinessStatus.BLOCKED
    result = RecommendationReadiness.model_validate({**fields, "input_mode": "REAL_VERIFIED", "quote_kind": "PUBLIC_RESEARCH_QUOTE"})
    assert result.research_readiness is ReadinessStatus.PASS
    assert result.recommendation_readiness is ReadinessStatus.PASS
    assert result.manual_execution_readiness is ReadinessStatus.BLOCKED
    fixture = RecommendationReadiness.model_validate({**fields, "input_mode": "FIXTURE"})
    assert fixture.recommendation_readiness is ReadinessStatus.BLOCKED
    assert RecommendationReadiness(runtime_health=ReadinessStatus.PASS).research_status is ReadinessStatus.NOT_RUN


@pytest.mark.parametrize("offset,code", [(0, "ACCOUNT_SNAPSHOT_VALID"), (-3601, "ACCOUNT_SNAPSHOT_STALE"), (1, "ACCOUNT_SNAPSHOT_FUTURE_DATED")])
def test_snapshot_time_bounds(tmp_path: Path, offset: int, code: str) -> None:
    now = datetime(2026, 9, 8, 14, tzinfo=UTC)
    path = envelope(tmp_path / "账户 # 空格.json", now + timedelta(seconds=offset))
    result, _ = inspect_snapshot(path, max_age_seconds=3600, checked_at=now, replay=True)
    assert result.code == code
    assert result.provenance_status is ReadinessStatus.UNKNOWN
    assert "cash" not in result.model_dump_json()


@pytest.mark.parametrize("now", [datetime(2026, 3, 8, 7, 5, tzinfo=UTC), datetime(2026, 11, 1, 6, 5, tzinfo=UTC)])
def test_dst_offsets_use_elapsed_time(tmp_path: Path, now: datetime) -> None:
    source_time = (now - timedelta(minutes=10)).astimezone(ZoneInfo("America/New_York"))
    result, _ = inspect_snapshot(envelope(tmp_path / "dst.json", source_time), max_age_seconds=900, checked_at=now, replay=True)
    assert result.status is ReadinessStatus.PASS
    assert result.age_seconds == 600


@pytest.mark.parametrize("change", [{"as_of": "2026-09-08T14:00:00"}, {"cash": "invalid"}])
def test_malformed_or_naive_snapshot_is_bounded(tmp_path: Path, change: dict) -> None:
    path = envelope(tmp_path / "bad.json", datetime.now(UTC), **change)
    result, account = inspect_snapshot(path, max_age_seconds=900)
    assert result.code == "ACCOUNT_SNAPSHOT_INVALID" and account is None


def test_pending_and_partial_input_not_usable(tmp_path: Path) -> None:
    for change in ({"coverage_status": "PARTIAL"}, {"pending_or_unknown_state": "pending settlement"}):
        result, _ = inspect_snapshot(envelope(tmp_path / "partial.json", datetime.now(UTC), **change), max_age_seconds=900)
        assert result.status is ReadinessStatus.BLOCKED


def test_duplicate_claim_is_atomic_and_conflict_visible(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "db.sqlite3")
    store.migrate()
    def claim(_: int) -> str:
        return store.snapshot_novelty("key", "facts", seen_at=datetime.now(UTC).isoformat())
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, range(2))) == ["NEW", "REPLAYED"]
    assert store.snapshot_novelty("key", "different") == "CONFLICT"
    assert store.snapshot_novelty("renamed", "facts") == "REPLAYED"


def test_old_database_upgrade_and_failed_migration_rollback(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY); INSERT INTO schema_migrations VALUES(1); CREATE TABLE user_table(value TEXT); INSERT INTO user_table VALUES('keep');")
    store = AuditStore(path)
    store.migrate()
    store.migrate()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT value FROM user_table").fetchone()[0] == "keep"
    bad = tmp_path / "migration-collision.sqlite3"
    with closing(sqlite3.connect(bad)) as connection, connection:
        connection.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY); INSERT INTO schema_migrations VALUES(1); CREATE VIEW snapshot_receipts AS SELECT 1;")
    with pytest.raises(sqlite3.DatabaseError):
        AuditStore(bad).migrate()
    with closing(sqlite3.connect(bad)) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 1
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='runs'").fetchone() is None




def test_session_boundaries_and_future_bar() -> None:
    policy = FreshnessPolicy(daily_bar_max_age_sessions=0)
    holiday = datetime(2026, 9, 7, 18, tzinfo=UTC)
    assert session_context(holiday) == "CLOSED"
    assert policy.daily_bar_is_current(date(2026, 9, 4), as_of=holiday)
    assert not policy.daily_bar_is_current(date(2026, 9, 8), as_of=holiday)
    assert session_context(datetime(2026, 9, 8, 12, tzinfo=UTC)) == "PRE_MARKET"
    assert session_context(datetime(2026, 9, 8, 14, tzinfo=UTC)) == "REGULAR"
    assert session_close(date(2026, 11, 27)).hour == 18


def test_stale_primary_valid_secondary_and_cached_replay(tmp_path: Path) -> None:
    from test_operational_data import NOW, Provider, quote

    from meridian.quotes import QuoteProviderTimeout

    stale = quote(price="50", observed=NOW - timedelta(minutes=16))
    fresh = quote()
    result = OperationalRefreshService(Provider("primary", stale), Provider("secondary", fresh)).refresh("AAPL", analysis_time=NOW)
    assert result.selected and result.selected.price == fresh.last
    assert result.conflict_percent is None
    cache = OperationalCache(tmp_path)
    from meridian.operational_data import OperationalQuote
    cache.store(OperationalQuote.from_shadow_quote(fresh))
    offline = OperationalRefreshService(Provider("fixture", QuoteProviderTimeout()), Provider("secondary", QuoteProviderTimeout()), cache=cache)
    assert offline.refresh("AAPL", analysis_time=NOW).cache_hit
    assert offline.refresh("AAPL", analysis_time=NOW - timedelta(seconds=1)).selected is None


def test_mid_migration_failure_rolls_back_new_tables(tmp_path: Path) -> None:
    path = tmp_path / "trigger.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY); INSERT INTO schema_migrations VALUES(1); CREATE TRIGGER reject_upgrade BEFORE INSERT ON schema_migrations WHEN NEW.version=2 BEGIN SELECT RAISE(ABORT, 'test failure'); END;")
    with pytest.raises(sqlite3.DatabaseError):
        AuditStore(path).migrate()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 1
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='run_readiness'").fetchone() is None


def test_historical_receipt_after_replay_cutoff_rejected(monkeypatch) -> None:
    from test_operational_market_snapshot import NOW, Bars, QuoteProvider, observation

    import meridian.operational_data as data_module
    import meridian.operational_market_snapshot as market_module
    from meridian.quotes import QuoteProviderTimeout

    class LaterBars(Bars):
        def get_series(self, *args, **kwargs):
            series = super().get_series(*args, **kwargs)
            return series.model_copy(update={"bars": tuple(bar.model_copy(update={"retrieved_at": NOW + timedelta(seconds=1)}) for bar in series.bars)})

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (NOW + timedelta(seconds=2)).astimezone(tz or UTC)

    service = market_module.OperationalMarketSnapshotService(OperationalRefreshService(
        QuoteProvider("primary", observation()), QuoteProvider("secondary", QuoteProviderTimeout())), LaterBars())
    fixed = service.build(["AAPL"], analysis_time=NOW)
    assert not fixed.quotes
    # Explicit live mode closes the cutoff after receipt; fixed replay does not.
    monkeypatch.setattr(data_module, "datetime", Clock)
    monkeypatch.setattr(market_module, "datetime", Clock)
    live = service.build(["AAPL"], analysis_time=NOW, live=True)
    assert live.quotes
    assert live.information_cutoff == NOW + timedelta(seconds=2)


def test_cache_lookup_preserves_requested_provider_alias(tmp_path: Path) -> None:
    from test_operational_data import NOW, Provider, quote

    from meridian.quotes import QuoteProviderTimeout

    cache = OperationalCache(tmp_path)
    online = OperationalRefreshService(Provider("primary", QuoteProviderTimeout()), Provider("secondary-alias", quote()), cache=cache)
    assert online.refresh("AAPL", analysis_time=NOW).selected is not None
    offline = OperationalRefreshService(Provider("primary", QuoteProviderTimeout()), Provider("secondary-alias", QuoteProviderTimeout()), cache=cache)
    result = offline.refresh("AAPL", analysis_time=NOW)
    assert result.cache_hit
    assert result.selected and result.selected.provider == "fixture"


def test_historical_adapter_never_advances_fixed_cutoff() -> None:
    from test_gate3b5_real_providers import AS_OF, _chart_payload, _Response

    from meridian.historical import YahooChartHistoricalProvider
    from meridian.security_master import DEFAULT_SECURITY_MASTER

    received = AS_OF + timedelta(seconds=1)
    provider = YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER,
        opener=lambda *a, **k: _Response(_chart_payload()), clock=lambda: received)
    with pytest.raises(ValueError):
        provider.get_series("AAPL", date(2026, 8, 27), date(2026, 8, 29), as_of=AS_OF)
    live = provider.get_series("AAPL", date(2026, 8, 27), date(2026, 8, 29), as_of=AS_OF, live=True)
    assert live.as_of == received
    assert all(bar.available_at <= live.as_of and bar.retrieved_at <= live.as_of for bar in live.bars)


def test_recent_timestamp_during_holiday_is_not_a_fresh_trade() -> None:
    from decimal import Decimal

    from meridian.operational_data import OperationalProviderStatus, OperationalQuote

    holiday = datetime(2026, 9, 7, 14, tzinfo=UTC)
    observation = OperationalQuote(
        symbol="AAPL", price=Decimal("100"), timestamp=holiday,
        received_at=holiday, provider="synthetic", source_type="PUBLIC_SHADOW_LAST",
        currency="USD", session="UNKNOWN")
    assert FreshnessPolicy().quote_status(observation, as_of=holiday) is OperationalProviderStatus.INVALID_RESPONSE


def test_every_nonpassing_dimension_blocks_recommendation() -> None:
    for state in ReadinessStatus:
        if state is ReadinessStatus.PASS:
            continue
        result = RecommendationReadiness(runtime_health=state)
        assert result.recommendation_readiness is ReadinessStatus.BLOCKED
        assert result.manual_execution_readiness is ReadinessStatus.BLOCKED


def test_final_probe_and_provider_health_use_same_cutoff(monkeypatch) -> None:
    from test_operational_market_snapshot import NOW, Bars, QuoteProvider, observation

    import meridian.operational_data as data_module
    import meridian.operational_market_snapshot as market_module
    from meridian.quotes import QuoteProviderTimeout

    finished = [NOW]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return finished[0].astimezone(tz or UTC)

    class SlowBars(Bars):
        def get_series(self, *args, **kwargs):
            result = super().get_series(*args, **kwargs)
            finished[0] = NOW + timedelta(seconds=901)
            return result

    monkeypatch.setattr(data_module, "datetime", Clock)
    monkeypatch.setattr(market_module, "datetime", Clock)
    service = market_module.OperationalMarketSnapshotService(OperationalRefreshService(
        QuoteProvider("primary", observation()), QuoteProvider("secondary", QuoteProviderTimeout())), SlowBars())
    result = service.build(["AAPL"], analysis_time=NOW, live=True)
    assert not result.quotes
    assert result.provider_health["AAPL"]["primary"] == "STALE"
    probe = result.provider_probes["AAPL"]["primary"]
    assert isinstance(probe, dict)
    assert probe["status"] == "STALE" and probe["error_category"] == "DATA_QUALITY"
