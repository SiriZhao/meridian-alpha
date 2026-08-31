"""Adversarial Gate 5E/5F replay and challenger integrity tests."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.challenger import ModelArtifactManifest, ModelArtifactStatus
from meridian.reproducibility import (
    CACHE_SCHEMA_VERSION,
    CachedObservation,
    ReplaySafeObservationCache,
    offline_reliability_soak,
    validate_frozen_llm_response,
)

T = datetime(2026, 8, 30, tzinfo=UTC)
H = hashlib.sha256(b"source").hexdigest()


def _record(*, payload=None, available_at=T, schema_version="1") -> CachedObservation:
    return CachedObservation(
        cache_key="sec:AAPL:fact:revenue",
        observation_type="fundamental",
        provider="sec",
        schema_version=schema_version,
        available_at=available_at,
        retrieved_at=T,
        source_hash=H,
        payload=payload or {"value": "1"},
    )


def test_cache_persists_and_validates_file_and_record_hashes(tmp_path) -> None:
    path = tmp_path / "cache.json"
    cache = ReplaySafeObservationCache(path)
    cache.put(_record())
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CACHE_SCHEMA_VERSION
    assert raw["cache_schema_version"] == CACHE_SCHEMA_VERSION
    assert raw["file_hash"] and raw["content_hash"]
    assert raw["records"][0]["record_hash"]
    assert ReplaySafeObservationCache(path).get("sec:AAPL:fact:revenue") is not None

    raw["records"][0]["payload"]["value"] = "2"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="CACHE_CORRUPT"):
        ReplaySafeObservationCache(path)


def test_cache_load_rejects_conflicting_duplicate_key(tmp_path) -> None:
    path = tmp_path / "cache.json"
    first = _record()
    second = _record(available_at=T + timedelta(minutes=1))
    records = [first.model_dump(mode="json"), second.model_dump(mode="json")]
    content = ReplaySafeObservationCache._content_digest(records)
    created = T.isoformat()
    file_hash = ReplaySafeObservationCache._file_digest(CACHE_SCHEMA_VERSION, created, records, content)
    path.write_text(
        json.dumps({
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "created_at": created,
            "records": records,
            "content_hash": content,
            "file_hash": file_hash,
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CACHE_CORRUPT"):
        ReplaySafeObservationCache(path)


@pytest.mark.parametrize("payload", [
    {"account_number": "redacted"},
    {"refresh_token": "redacted"},
    {"raw_connector_data": {"x": 1}},
])
def test_cache_blocks_sensitive_payload_names(payload) -> None:
    with pytest.raises(ValueError, match="SENSITIVE"):
        _record(payload=payload)


def test_frozen_llm_response_requires_exact_hash_cutoff_schema_and_citations() -> None:
    response = {
        "schema_version": "1",
        "decision_as_of": T.isoformat(),
        "direction": "NEUTRAL",
        "conviction": "0.5",
        "thesis": "No directional conclusion.",
        "cited_evidence_ids": ["e1"],
    }
    digest = hashlib.sha256(json.dumps(response, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert validate_frozen_llm_response(
        response,
        expected_hash=digest,
        decision_as_of=T,
        allowed_evidence_ids={"e1"},
    )["direction"] == "NEUTRAL"
    with pytest.raises(ValueError, match="CITATION_NOT_CERTIFIED"):
        bad_response = {**response, "cited_evidence_ids": ["future"]}
        bad_digest = hashlib.sha256(
            json.dumps(bad_response, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        validate_frozen_llm_response(
            bad_response,
            expected_hash=bad_digest,
            decision_as_of=T,
            allowed_evidence_ids={"e1"},
        )


def test_oos_status_cannot_use_placeholder_validation_fields() -> None:
    with pytest.raises(ValueError, match="OOS_VALIDATION_MISSING"):
        ModelArtifactManifest(
            model_id="m",
            model_type="development",
            model_hash=H,
            artifact_path="missing.bin",
            framework_version="unavailable",
            framework_commit="1234567",
            training_code_commit="7654321",
            trained_at=T,
            training_start=T - timedelta(days=30),
            training_end=T - timedelta(days=1),
            information_cutoff=T - timedelta(days=1),
            universe=("AAPL",),
            feature_schema="v1",
            feature_versions={"x": "1"},
            target_objective="long_only",
            action_space="target_weights",
            random_seed=1,
            hyperparameter_hash=H,
            normalization_state_hash=H,
            transaction_cost_assumption=Decimal("0.001"),
            benchmark="SPY",
            validation_period="not_run",
            oos_period="not_run",
            oos_metrics={"return": Decimal("0")},
            walk_forward_status="NOT_RUN",
            provenance="test",
            status=ModelArtifactStatus.OOS_VALIDATED_SHADOW,
        )


def test_offline_soak_is_bounded_and_explicit() -> None:
    report = offline_reliability_soak(cycles=4)
    assert report["network_calls"] == 0
    assert report["retries"] == 0
    assert len(report["scenarios"]) >= 20
    assert set(report["scenarios"].values()) == {"EXPLICIT_FAIL_CLOSED"}
