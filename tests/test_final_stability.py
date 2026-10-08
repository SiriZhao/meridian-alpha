"""Crash-safe persistence and cache corruption regressions."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from meridian.application import MeridianApplicationService
from meridian.corporate_actions import CorporateActionEvent, CorporateActionType, FirstSeenLedger
from meridian.daily_closure import persist_report_content
from meridian.data.retrieval_orchestrator import EvidenceCache
from meridian.long_shadow import (
    ExecutionAssumption,
    OutcomeHorizon,
    ShadowPerformanceLedger,
    ShadowPerformanceRecord,
    ShadowRunLedger,
    ShadowSessionLedger,
    ShadowSessionRecord,
    derive_daily_health,
)
from meridian.provider_resilience import ProviderHealthStore
from meridian.report_bundle import verify_report_bundle
from meridian.reproducibility import ReplaySafeObservationCache
from meridian.runtime import RuntimePaths
from meridian.runtime_io import FilesystemFailure, atomic_write, run_lock
from scripts.safe_acceptance import fixture as acceptance_fixture
from tests.retrieval_helpers import NOW, requirement
from tests.test_gate5e_5f_integrity import _record
from tests.test_gate6d_6e_long_shadow import _run


def event(symbol: str) -> CorporateActionEvent:
    return CorporateActionEvent(canonical_asset_id="US-EQ-" + symbol, canonical_symbol=symbol,
                                action_type=CorporateActionType.SPLIT, event_date=date(2026, 9, 1),
                                ratio=Decimal("2"), provider="fixture", source="fixture", first_seen_at=NOW)


@pytest.mark.parametrize("payload", ["null", "[]", "42", '"string"', "{}", '{"evidence":null}', "", "{", '{"evidence":{}}'])
def test_evidence_cache_wrong_shapes_are_cache_misses(tmp_path: Path, payload: str) -> None:
    cache = EvidenceCache(tmp_path, clock=lambda: NOW)
    cache._path(requirement(), NOW).write_text(payload, encoding="utf-8")
    assert cache.load(requirement(), as_of=NOW) == ()


def test_first_seen_stale_instances_do_not_lose_updates(tmp_path: Path) -> None:
    path = tmp_path / "first-seen.json"
    first = FirstSeenLedger(path, clock=lambda: NOW)
    second = FirstSeenLedger(path, clock=lambda: NOW)
    initial = first.record(event("AAPL"))
    second.record(event("SPY"))
    assert first.record(event("AAPL")) == initial
    assert len(FirstSeenLedger(path).rows) == 2


def test_first_seen_failure_rolls_back_disk_and_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "first-seen.json"
    ledger = FirstSeenLedger(path, clock=lambda: NOW)
    ledger.record(event("AAPL"))
    original = path.read_bytes()
    def fail(*args: object) -> None:
        raise PermissionError(13, "locked destination")
    monkeypatch.setattr("meridian.corporate_actions.atomic_write", fail)
    with pytest.raises(PermissionError):
        ledger.record(event("SPY"))
    assert len(ledger.rows) == 1
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_first_seen_writer_contention_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "first-seen.json"
    with run_lock(tmp_path, "other", name=path.name + ".writer"):
        with pytest.raises(OSError, match="LOCK_ACTIVE_DUPLICATE_PROCESS"):
            FirstSeenLedger(path, clock=lambda: NOW).record(event("AAPL"))
    assert not path.exists()


def test_first_seen_duplicate_disk_rows_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "first-seen.json"
    FirstSeenLedger(path, clock=lambda: NOW).record(event("AAPL"))
    rows = json.loads(path.read_text())
    path.write_text(json.dumps(rows + rows), encoding="utf-8")
    with pytest.raises(ValueError, match="DUPLICATE_EVENT"):
        FirstSeenLedger(path)


@pytest.mark.parametrize("content", ["", "null", "{}", "["])
def test_corrupt_first_seen_state_never_becomes_empty_valid_state(tmp_path: Path, content: str) -> None:
    path = tmp_path / "first-seen.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        FirstSeenLedger(path)
    assert path.read_text() == content


def test_provider_health_closes_connection_on_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = sqlite3.connect
    opened: list[sqlite3.Connection] = []
    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection
    monkeypatch.setattr("meridian.provider_resilience.sqlite3.connect", connect)
    store = ProviderHealthStore(tmp_path / "health.sqlite3")
    def record() -> dict[str, object]:
        return store.record(provider="fixture", symbol="SPY", channel="QUOTE", category=None, latency_ms=1,
                            completed_at=datetime(2026, 10, 7, tzinfo=UTC), fallback=False)
    assert record()["recent_successes"] == 1
    with original(store.path) as connection:
        connection.execute("DROP TABLE attempts")
        connection.execute("CREATE TABLE attempts(wrong_column TEXT)")
    with pytest.raises(sqlite3.DatabaseError):
        record()
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_atomic_interruption_before_rename_preserves_prior_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "state.json"
    atomic_write(path, '{"state":"original"}')
    original = path.read_bytes()
    def fail(*args: object) -> None:
        raise PermissionError(13, "rename denied")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(FilesystemFailure) as error:
        atomic_write(path, '{"state":"new"}')
    assert error.value.detail["operation"] == "ATOMIC_REPLACE"
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("payload", ["null", "[]", "42", "{}"])
def test_wrong_report_receipt_shapes_fail_closed(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "report_bundle.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="REPORT_BUNDLE_INCOMPLETE"):
        verify_report_bundle(path)


@pytest.mark.parametrize("payload", ["", "null", "[]", "{}", '{"pid":"invalid","hostname":"local","process_start_time":"0"}'])
def test_corrupt_lock_metadata_preserved_and_classified(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "production.lock"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(OSError, match="LOCK_METADATA_CORRUPT"), run_lock(tmp_path, "blocked"):
        pytest.fail("corrupt ownership must not grant a lock")
    assert path.read_text() == payload


def test_report_publication_failure_leaves_no_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "daily.json"
    def fail(*args: object) -> None:
        raise PermissionError(13, "publication denied")
    monkeypatch.setattr("meridian.daily_closure.publish_staged_report", fail)
    with pytest.raises(PermissionError):
        persist_report_content(path, "synthetic report")
    assert not list(tmp_path.iterdir())


def test_parallel_paper_lifecycle_rejected_before_research(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path))
    service.paper_init()
    def forbidden(*args, **kwargs):
        pytest.fail("concurrent launch must stop before daily research")
    monkeypatch.setattr(service, "daily", forbidden)
    lock_name = "paper-" + hashlib.sha256(b"Schwab-Paper").hexdigest()[:24]
    with run_lock(service.paths.locks, "other-run", name=lock_name):
        with pytest.raises(OSError, match="LOCK_ACTIVE_DUPLICATE_PROCESS"):
            service.paper_run()
    assert service.paper_trades()["trades"] == []


def performance_row(run_id: str = "r1") -> ShadowPerformanceRecord:
    return ShadowPerformanceRecord(run_id=run_id, ticker="AAPL", decision_as_of=NOW, horizon=OutcomeHorizon.D1,
                                   recommendation_weight=Decimal("0.1"), target_weight=Decimal("0.1"),
                                   execution_assumption=ExecutionAssumption.NEXT_SESSION_OPEN)


def test_mature_shadow_outcome_can_join_once_and_survive_reload(tmp_path: Path) -> None:
    path = tmp_path / "performance.json"
    ledger = ShadowPerformanceLedger(path)
    ledger.add(performance_row())
    def join() -> ShadowPerformanceRecord:
        return ledger.join_forward_outcome(("r1", "AAPL", OutcomeHorizon.D1), outcome_return=Decimal("0.01"), available_at=NOW + timedelta(days=1), observed_at=NOW + timedelta(days=2))
    key = ("r1", "AAPL", OutcomeHorizon.D1)
    joined = join()
    assert joined.actual_outcome_return == Decimal("0.01")
    assert ShadowPerformanceLedger(path).records == (joined,)
    assert join() == joined
    with pytest.raises(ValueError, match="IMMUTABLE"):
        ledger.join_forward_outcome(key, outcome_return=Decimal("0.02"), available_at=NOW + timedelta(days=1), observed_at=NOW + timedelta(days=2))


@pytest.mark.parametrize("bad_return", ["NaN", "Infinity", "-Infinity"])
def test_shadow_outcome_nonfinite_return_is_rejected(bad_return: str) -> None:
    ledger = ShadowPerformanceLedger()
    ledger.add(performance_row())
    with pytest.raises(ValueError):
        ledger.join_forward_outcome(("r1", "AAPL", OutcomeHorizon.D1), outcome_return=Decimal(bad_return),
                                    available_at=NOW + timedelta(days=1), observed_at=NOW + timedelta(days=2))
    assert ledger.records[0].actual_outcome_return is None


@pytest.mark.parametrize("kind", ["runs", "sessions", "performance", "replay"])
def test_legacy_stores_merge_stale_instances_and_rollback_failed_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    first: Any
    second: Any
    rows: list[Any]
    path = tmp_path / (kind + ".json")
    if kind == "runs":
        first, second = ShadowRunLedger(path), ShadowRunLedger(path)
        rows = [_run().model_copy(update={"run_id": key}) for key in ("r1", "r2", "r3")]
        write_first, write_second = first.append, second.append
        module = "meridian.long_shadow"
    elif kind == "sessions":
        first, second = ShadowSessionLedger(path), ShadowSessionLedger(path)
        rows = [ShadowSessionRecord(run_id=key, decision_as_of=NOW, code_commit="fixture", skill_version="fixture", skill_zip_hash="fixture") for key in ("r1", "r2", "r3")]
        write_first, write_second = first.append, second.append
        module = "meridian.long_shadow"
    elif kind == "performance":
        first, second = ShadowPerformanceLedger(path), ShadowPerformanceLedger(path)
        rows = [performance_row(key) for key in ("r1", "r2", "r3")]
        write_first, write_second = first.add, second.add
        module = "meridian.long_shadow"
    else:
        first, second = ReplaySafeObservationCache(path), ReplaySafeObservationCache(path)
        rows = [type(_record()).model_validate(_record().model_dump(exclude={"record_hash"}) | {"cache_key": key}) for key in ("r1", "r2", "r3")]
        write_first, write_second = first.put, second.put
        module = "meridian.reproducibility"
    write_first(rows[0])
    write_second(rows[1])
    original = path.read_bytes()
    def fail(*args: object) -> None:
        raise PermissionError(13, "denied")
    monkeypatch.setattr(module + ".atomic_write", fail)
    with pytest.raises((OSError, ValueError)):
        write_first(rows[2])
    assert len(first.records) == 2
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("components", [{}, {"market": "NOT_RUN"}, {"quote": "unexpected-new-status"}])
def test_missing_or_unknown_legacy_health_is_never_green(components: dict[str, str]) -> None:
    health = derive_daily_health(components, manual_gates_pass=True)
    assert health.level.value == "YELLOW"
    assert health.reasons
    assert not health.manual_entry_allowed


@pytest.mark.parametrize("missing", ["run_health_json", "paper_report_json", "paper_report_markdown"])
def test_ledger_owner_survives_missing_report_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    import meridian.application as application
    import scripts.safe_acceptance as acceptance
    monkeypatch.setattr(application, "datetime", acceptance.FixtureClock)
    monkeypatch.setattr(acceptance, "datetime", acceptance.FixtureClock)
    service = MeridianApplicationService(RuntimePaths(tmp_path))
    service.paper_init()
    monkeypatch.setattr(service, "daily", lambda *args, **kwargs: acceptance_fixture("SYNTHETIC_FILL"))
    first = service.paper_run(run_purpose="ACCEPTANCE_VALIDATION")
    assert first["status"] == "PAPER_READY"
    outputs = first["output_files"]
    assert isinstance(outputs, dict)
    Path(str(outputs[missing])).unlink()
    def forbidden(*args, **kwargs):
        pytest.fail("missing projection must not re-execute an owned paper day")
    monkeypatch.setattr(service, "daily", forbidden)
    duplicate = service.paper_run(run_purpose="ACCEPTANCE_VALIDATION")
    assert duplicate["status"] == "PAPER_ALREADY_EXECUTED"
    assert len(service.paper_trades()["trades"]) == 1  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        verify_report_bundle(Path(str(outputs["report_bundle_json"])))


def test_orphan_report_cannot_create_ledger_or_run_authority(tmp_path: Path) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path))
    directory = service.paths.reports / "orphan"
    directory.mkdir(parents=True)
    (directory / "run_health.json").write_text('{"status":"PASS"}', encoding="utf-8")
    result = service.paper_run()
    assert result["status"] == "PAPER_BLOCKED"
    assert not service.paths.db.exists()
