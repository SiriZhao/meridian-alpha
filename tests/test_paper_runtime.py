from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from meridian.application import MeridianApplicationService
from meridian.audit import SCHEMA_VERSION, AuditStore
from meridian.config import load_policies
from meridian.host_readiness import ReadinessStatus, inspect_snapshot
from meridian.paper import DEFAULT_ACCOUNT, PaperLedger, PaperOrderIntent, PaperSettings
from meridian.runtime import RuntimePaths, policy_directory
from meridian.schemas import Side


def ledger(tmp_path: Path) -> PaperLedger:
    return PaperLedger(AuditStore(tmp_path / "meridian.sqlite3"), PaperSettings())


def intent(
    order_id: str, ticker: str, side: Side, quantity: str, price: str = "100"
) -> PaperOrderIntent:
    return PaperOrderIntent(
        order_id,
        ticker,
        side,
        Decimal(quantity),
        Decimal(price),
        "yahoo-public",
    )


def test_v2_database_upgrades_to_paper_schema_without_losing_user_table(tmp_path: Path) -> None:
    path = tmp_path / "v2.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY);"
            "INSERT INTO schema_migrations VALUES(2);"
            "CREATE TABLE user_table(value TEXT);"
            "INSERT INTO user_table VALUES('keep');"
        )
    AuditStore(path).migrate()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 3
        assert connection.execute("SELECT value FROM user_table").fetchone()[0] == "keep"
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='paper_accounts'").fetchone()

def test_paper_initialization_is_once_and_survives_restart(tmp_path: Path) -> None:
    first = ledger(tmp_path)
    account, created = first.initialize(DEFAULT_ACCOUNT)
    assert created
    assert account.cash == Decimal("100000.00")
    second = ledger(tmp_path)
    existing, created = second.initialize(DEFAULT_ACCOUNT, cash=Decimal("1"))
    assert not created
    assert existing.cash == Decimal("100000.00")
    assert existing.positions == ()
    assert SCHEMA_VERSION == 3


def test_paper_snapshot_is_fresh_ledger_observation_not_a_renamed_replay(tmp_path: Path) -> None:
    store = AuditStore(tmp_path / "meridian.sqlite3")
    paper = PaperLedger(store)
    paper.initialize()
    start = datetime(2026, 9, 8, 14, 0, tzinfo=UTC)
    first_path = paper.write_snapshot(tmp_path / "中文 空格 #", observed_at=start)
    second_path = paper.write_snapshot(tmp_path / "中文 空格 #", observed_at=start + timedelta(minutes=1))
    first, _ = inspect_snapshot(first_path, max_age_seconds=3600, checked_at=start, replay=True)
    second, _ = inspect_snapshot(second_path, max_age_seconds=3600, checked_at=start + timedelta(minutes=1), replay=True)
    assert first.status is ReadinessStatus.PASS
    assert first.source_kind == "PAPER_LEDGER"
    assert first.provenance_status is ReadinessStatus.PASS
    assert first.content_hash != second.content_hash
    assert store.snapshot_novelty(first.snapshot_key or "", first.content_hash or "", seen_at=start.isoformat()) == "NEW"
    assert store.snapshot_novelty(first.snapshot_key or "", first.content_hash or "") == "REPLAYED"
    assert store.snapshot_novelty(second.snapshot_key or "", second.content_hash or "", seen_at=(start + timedelta(minutes=1)).isoformat()) == "NEW"


def test_paper_fill_is_atomic_long_only_and_daily_idempotent(tmp_path: Path) -> None:
    paper = ledger(tmp_path)
    paper.initialize(cash=Decimal("1000"))
    status, fills = paper.execute(
        DEFAULT_ACCOUNT,
        trading_date="2026-09-08",
        canonical_run_id="daily-one",
        intents=(intent("buy-1", "AAPL", Side.BUY, "5"),),
        now=datetime(2026, 9, 8, 14, tzinfo=UTC),
    )
    assert status == "PAPER_COMPLETE"
    assert len(fills) == 1
    current = paper.state()
    assert current is not None
    assert current.positions[0].ticker == "AAPL"
    assert current.positions[0].quantity == Decimal("5")
    assert current.cash < Decimal("500")
    again, duplicate = paper.execute(
        DEFAULT_ACCOUNT,
        trading_date="2026-09-08",
        canonical_run_id="daily-two",
        intents=(intent("buy-duplicate", "AAPL", Side.BUY, "5"),),
    )
    assert again == "PAPER_ALREADY_EXECUTED"
    assert duplicate == ()
    with pytest.raises(ValueError, match="PAPER_LONG_ONLY_OVERSELL"):
        paper.execute(
            DEFAULT_ACCOUNT,
            trading_date="2026-09-09",
            canonical_run_id="daily-three",
            intents=(intent("oversell", "AAPL", Side.SELL, "6"),),
        )
    after = paper.state()
    assert after is not None and after.positions[0].quantity == Decimal("5")


def test_paper_accounting_benchmark_and_drawdown(tmp_path: Path) -> None:
    paper = ledger(tmp_path)
    paper.initialize(cash=Decimal("1000"))
    _, fills = paper.execute(
        DEFAULT_ACCOUNT,
        trading_date="2026-09-08",
        canonical_run_id="daily-one",
        intents=(intent("buy-1", "AAPL", Side.BUY, "5", "100"),),
    )
    first = paper.record_nav(
        DEFAULT_ACCOUNT,
        trading_date="2026-09-08",
        canonical_run_id="daily-one",
        quotes={"AAPL": {"last": "100"}, "SPY": {"last": "500"}},
        fills=fills,
    )
    assert first is not None and first["benchmark_cumulative_return"] == "0.0000"
    second = paper.record_nav(
        DEFAULT_ACCOUNT,
        trading_date="2026-09-09",
        canonical_run_id="daily-two",
        quotes={"AAPL": {"last": "90"}, "SPY": {"last": "495"}},
    )
    assert second is not None
    assert Decimal(str(second["daily_return"])) < 0
    assert Decimal(str(second["drawdown"])) < 0
    assert Decimal(str(second["benchmark_cumulative_return"])) < 0


def test_paper_reset_requires_exact_account_confirmation(tmp_path: Path) -> None:
    paper = ledger(tmp_path)
    paper.initialize()
    with pytest.raises(ValueError, match="PAPER_RESET_CONFIRMATION_REQUIRED"):
        paper.reset(DEFAULT_ACCOUNT, confirmation="wrong")
    assert paper.state() is not None
    paper.reset(DEFAULT_ACCOUNT, confirmation=DEFAULT_ACCOUNT)
    assert paper.state() is None


def _canonical_daily_payload() -> dict[str, object]:
    cutoff = "2026-09-08T14:00:00+00:00"
    return {
        "run_id": "daily-paper-canonical",
        "analysis_time": cutoff,
        "information_cutoff": cutoff,
        "trading_date": "2026-09-08",
        "status": "DRAFT",
        "runtime_status": "PASS",
        "data_status": "PASS",
        "research_status": "AVAILABLE",
        "portfolio": {"positions": [{"ticker": "AAPL", "target_weight": "0.10"}]},
        "market_observations": {
            "AAPL": {"last": "100", "timestamp": cutoff, "freshness_state": "VERIFIED", "provider": "yahoo"},
            "SPY": {"last": "500", "timestamp": cutoff, "freshness_state": "VERIFIED", "provider": "yahoo"},
        },
        "provider_probes": {"AAPL": {"selected_provider": "yahoo"}},
        "research": {"status": "AVAILABLE", "provider": "deepseek", "model": "configured"},
        "decision_context": {"status": "AVAILABLE"},
        "gates": [],
        "readiness": {"recommendation_readiness": "BLOCKED"},
        "manual_authority": {"status": "BLOCKED"},
        "output_files": {},
    }


def test_paper_run_uses_canonical_daily_then_prevents_same_day_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    service = MeridianApplicationService(paths)
    assert service.paper_init()["status"] == "PAPER_INITIALIZED"
    seen: list[Path] = []

    def canonical(snapshot: Path | None, market_fixture: Path | None = None, *, research_live_enabled: bool = False, run_purpose: str = "OPERATIONAL_DAILY") -> dict[str, object]:
        assert snapshot is not None and snapshot.is_file()
        diagnostic, _ = inspect_snapshot(snapshot, max_age_seconds=3600)
        assert diagnostic.source_kind == "PAPER_LEDGER"
        assert research_live_enabled and market_fixture is None
        assert run_purpose == "OPERATIONAL_PAPER_DAILY"
        seen.append(snapshot)
        return _canonical_daily_payload()

    monkeypatch.setattr(service, "daily", canonical)
    first = service.paper_run()
    assert first["status"] == "PAPER_READY"
    assert first["run_type"] == "PAPER_DAILY"
    assert first["run_purpose"] == "OPERATIONAL_PAPER_DAILY"
    assert first["paper_execution"]["quote_certification"] == "BLOCKED"  # type: ignore[index]
    assert first["manual_authority"] == "BLOCKED"
    outputs = first["output_files"]
    assert isinstance(outputs, dict)
    markdown = Path(str(outputs["paper_report_markdown"]))
    assert markdown.is_file()
    report_text = markdown.read_text(encoding="utf-8")
    for heading in (
        "# Meridian Daily — Schwab-Paper",
        "## Market",
        "## Today's Decisions",
        "## Risk",
        "## Today's Paper Trades",
        "## Research",
        "## Gates",
        "## Readiness",
        "## Blockers",
    ):
        assert heading in report_text
    second = service.paper_run()
    assert second["status"] == "PAPER_ALREADY_EXECUTED"
    assert len(service.paper_trades()["trades"]) == 1  # type: ignore[arg-type]
    history = service.paper_history()["history"]
    assert isinstance(history, list) and history[0]["trade_count"] == 1
    assert Decimal(str(history[0]["fees"])) > 0
    assert all(not item.exists() for item in seen)


def test_paper_run_fails_closed_when_canonical_research_is_not_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MeridianApplicationService(RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)}))
    assert service.paper_init()["status"] == "PAPER_INITIALIZED"
    payload = _canonical_daily_payload()
    payload["research_status"] = "NOT_CONFIGURED"

    seen_purposes: list[str] = []

    def canonical(snapshot: Path | None, market_fixture: Path | None = None, *, research_live_enabled: bool = False, run_purpose: str = "OPERATIONAL_DAILY") -> dict[str, object]:
        seen_purposes.append(run_purpose)
        return payload

    monkeypatch.setattr(service, "daily", canonical)
    result = service.paper_run(run_purpose="ACCEPTANCE_VALIDATION")
    assert result["status"] == "PAPER_BLOCKED"
    assert result["run_purpose"] == "ACCEPTANCE_VALIDATION"
    assert seen_purposes == ["ACCEPTANCE_VALIDATION"]
    assert "PAPER_EXECUTION_BLOCKED_RESEARCH_NOT_CONFIGURED" in result["blockers"]  # type: ignore[operator]
    assert service.paper_trades()["trades"] == []


def test_paper_run_never_creates_missing_database_or_account(tmp_path: Path) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path / "runtime")})
    service = MeridianApplicationService(paths)

    missing_database = service.paper_run()

    assert missing_database["status"] == "PAPER_BLOCKED"
    assert missing_database["error_code"] == "STORAGE_UNAVAILABLE"
    assert missing_database["auto_initialized"] is False
    assert not paths.db.exists()

    assert service.init()["status"] == "INIT_COMPLETE"
    missing_account = service.paper_run()
    assert missing_account["status"] == "PAPER_BLOCKED"
    assert missing_account["error_code"] == "PAPER_ACCOUNT_NOT_FOUND"
    assert missing_account["auto_initialized"] is False
    assert service._paper_ledger().state(DEFAULT_ACCOUNT) is None


def test_duplicate_paper_run_short_circuits_before_market_or_research(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    service = MeridianApplicationService(paths)
    assert service.paper_init()["status"] == "PAPER_INITIALIZED"
    trading_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    status, fills = service._paper_ledger().execute(
        DEFAULT_ACCOUNT,
        trading_date=trading_date,
        canonical_run_id="daily-authoritative",
        intents=(),
    )
    assert status == "PAPER_NO_TRADE" and fills == ()

    def should_not_run(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("duplicate invoked canonical research workflow")

    monkeypatch.setattr(service, "daily", should_not_run)
    monkeypatch.setattr(
        PaperLedger,
        "write_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate wrote snapshot")),
    )
    before = service._paper_ledger().state(DEFAULT_ACCOUNT)
    result = service.paper_run()
    after = service._paper_ledger().state(DEFAULT_ACCOUNT)

    assert result["status"] == "PAPER_ALREADY_EXECUTED"
    assert result["blockers"] == ["PAPER_DAILY_IDEMPOTENCY_ALREADY_EXECUTED"]
    lineage = result["idempotency"]
    assert isinstance(lineage, dict)
    assert lineage["attempted_run_id"] != lineage["authoritative_existing_run_id"]
    assert lineage["authoritative_existing_run_id"] == "daily-authoritative"
    assert lineage["ledger_mutated_current_run"] is False
    assert lineage["orders_created_current_run"] == 0
    assert lineage["fills_created_current_run"] == 0
    assert result["research"]["status"] == "SKIPPED"  # type: ignore[index]
    assert result["research"]["invoked_in_current_run"] is False  # type: ignore[index]
    assert result["decision"]["status"] == "SKIPPED"  # type: ignore[index]
    assert result["forward_evidence"]["status"] == "SKIPPED"  # type: ignore[index]
    outputs = result["output_files"]
    assert isinstance(outputs, dict)
    health = json.loads(Path(str(outputs["run_health_json"])).read_text(encoding="utf-8"))
    assert health["run_id"] == result["paper_run_id"]
    assert health["idempotency"]["attempted_run_id"] == lineage["attempted_run_id"]
    assert all(stage["status"] == "SKIPPED" for stage in health["stages"])
    assert all(stage.get("source_run_id") is None for stage in health["stages"])
    assert before == after


def test_failed_daily_row_does_not_trigger_early_duplicate_short_circuit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    service = MeridianApplicationService(paths)
    assert service.paper_init()["status"] == "PAPER_INITIALIZED"
    trading_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    with sqlite3.connect(paths.db) as connection:
        connection.execute(
            "INSERT INTO paper_daily_runs(account_name,trading_date,canonical_run_id,order_intent_hash,execution_status,created_at) VALUES(?,?,?,?,?,?)",
            (DEFAULT_ACCOUNT, trading_date, "daily-failed", "hash", "PAPER_BLOCKED", datetime.now(UTC).isoformat()),
        )
    called: list[str] = []

    def canonical(*args: object, **kwargs: object) -> dict[str, object]:
        called.append(str(kwargs.get("run_purpose")))
        return _canonical_daily_payload() | {"trading_date": trading_date}

    monkeypatch.setattr(service, "daily", canonical)
    result = service.paper_run()
    assert called == ["OPERATIONAL_PAPER_DAILY"]
    assert result["status"] == "PAPER_READY"
    assert service._paper_ledger().authoritative_daily_execution(DEFAULT_ACCOUNT, trading_date)["canonical_run_id"] == "daily-paper-canonical"  # type: ignore[index]


def test_late_duplicate_race_does_not_mark_nav_or_claim_fills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path))
    assert service.paper_init()["status"] == "PAPER_INITIALIZED"
    payload = _canonical_daily_payload()
    payload["status"] = "NO_ACTION"
    def canonical(*args, **kwargs):
        service._paper_ledger().execute(DEFAULT_ACCOUNT, trading_date=str(payload["trading_date"]),
            canonical_run_id="daily-race-winner", intents=())
        return payload
    monkeypatch.setattr(service, "daily", canonical)
    monkeypatch.setattr(PaperLedger, "record_nav", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate marked NAV")))
    result = service.paper_run()
    assert result["status"] == "PAPER_ALREADY_EXECUTED"
    assert result["idempotency"]["authoritative_existing_run_id"] == "daily-race-winner"  # type: ignore[index]
    assert result["idempotency"]["ledger_mutated_current_run"] is False  # type: ignore[index]
    assert result["paper_execution"]["intent_count"] == 0  # type: ignore[index]
    assert result["paper_execution"]["fills"] == []  # type: ignore[index]


def test_paper_execution_race_has_one_authoritative_owner(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    first = ledger(tmp_path)
    first.initialize()
    trading_date = "2099-01-03"

    def execute(run_id: str) -> str:
        return ledger(tmp_path).execute(
            DEFAULT_ACCOUNT,
            trading_date=trading_date,
            canonical_run_id=run_id,
            intents=(),
        )[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(execute, ("daily-race-a", "daily-race-b")))
    assert sorted(statuses) == ["PAPER_ALREADY_EXECUTED", "PAPER_NO_TRADE"]
    assert ledger(tmp_path).daily_execution(DEFAULT_ACCOUNT, trading_date) is not None


def test_paper_order_builder_applies_cash_and_existing_policy(tmp_path: Path) -> None:
    paper = ledger(tmp_path)
    paper.initialize(cash=Decimal("10000"))
    policies = load_policies(policy_directory())
    intents = paper.build_order_intents(
        DEFAULT_ACCOUNT,
        trading_date="2026-09-08",
        canonical_run_id="daily-one",
        targets=[{"ticker": "AAPL", "target_weight": "0.10"}],
        quotes={"AAPL": {"last": "100", "provider": "yahoo"}},
        risk=policies.risk,
        execution=policies.execution,
    )
    assert len(intents) == 1
    assert intents[0].quantity <= 50  # Existing max_single_order_nav_percent is 5%.
