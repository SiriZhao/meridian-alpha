from datetime import UTC, datetime
from pathlib import Path

import pytest

from meridian.long_shadow import ShadowSessionLedger, ShadowSessionRecord


def _record(run_id: str, **updates: object) -> ShadowSessionRecord:
    values: dict[str, object] = {
        "run_id": run_id,
        "decision_as_of": datetime(2026, 8, 31, 21, 0, tzinfo=UTC),
        "code_commit": "a" * 40,
        "skill_version": "meridian-alpha-skill-v1",
        "skill_zip_hash": "b" * 64,
        "us_trading_session_completed": True,
        "daily_run_completed": True,
        "no_p0": True,
        "no_readiness_bypass": True,
        "ledger_append_succeeded": True,
        "account_reconciliation_green": True,
        "provider_failure_states_explicit": True,
        "evidence_ids_valid": True,
    }
    values.update(updates)
    return ShadowSessionRecord.model_validate(values)


def test_session_requires_every_gate_and_counts_only_qualified(tmp_path: Path) -> None:
    ledger = ShadowSessionLedger(tmp_path / "sessions.json")
    incomplete = _record("incomplete", us_trading_session_completed=False)
    complete = _record("complete")
    ledger.append(incomplete)
    ledger.append(complete)
    assert incomplete.qualified is False
    assert "US_TRADING_SESSION_NOT_COMPLETED" in incomplete.incomplete_reasons
    assert complete.qualified is True
    assert ledger.completed_count == 1
    assert ledger.acceptance_status == "OBSERVATION_IN_PROGRESS"
    assert ledger.summary()["sessions_required"] == 5
    assert ledger.summary()["performance_validated"] is False


def test_session_duplicate_is_idempotent_and_conflict_fails_closed(tmp_path: Path) -> None:
    ledger = ShadowSessionLedger(tmp_path / "sessions.json")
    record = _record("same")
    assert ledger.append(record) == record
    assert ledger.append(record) == record
    with pytest.raises(ValueError, match="SHADOW_SESSION_IMMUTABLE"):
        ledger.append(_record("same", evidence_ids_valid=False))


def test_session_ledger_rejects_tampered_hash(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    ledger = ShadowSessionLedger(path)
    ledger.append(_record("tamper"))
    path.write_text(path.read_text(encoding="utf-8").replace('"content_hash":"', '"content_hash":"0', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="SHADOW_SESSION_CORRUPT"):
        ShadowSessionLedger(path)