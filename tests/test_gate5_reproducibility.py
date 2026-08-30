import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.reproducibility import (
    AnalysisRunManifest,
    CachedObservation,
    FrozenFeature,
    ProviderHealth,
    ProviderHealthStatus,
    ReplaySafeObservationCache,
)

T = datetime(2026, 8, 30, tzinfo=UTC)
H = hashlib.sha256(b"source").hexdigest()


def test_frozen_feature_blocks_future_inputs_and_is_deterministic() -> None:
    feature = FrozenFeature(
        asset="AAPL",
        as_of=T,
        available_at=T,
        features={"momentum": Decimal("0.1")},
        source_hashes=(H,),
        feature_version="v1",
        normalization_version="n1",
    )
    assert feature.content_hash == FrozenFeature.model_validate(feature.model_dump()).content_hash
    with pytest.raises(ValueError, match="after as_of"):
        FrozenFeature.model_validate(
            feature.model_copy(update={"available_at": T + timedelta(seconds=1)}).model_dump()
        )


def test_frozen_feature_rejects_non_sha256_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        FrozenFeature(
            asset="AAPL", as_of=T, available_at=T, features={"momentum": Decimal("0.1")},
            source_hashes=("not-a-hash",), feature_version="v1", normalization_version="n1",
        )
    with pytest.raises(ValueError, match="finite"):
        FrozenFeature(
            asset="AAPL", as_of=T, available_at=T, features={"momentum": Decimal("NaN")},
            source_hashes=(H,), feature_version="v1", normalization_version="n1",
        )


def test_analysis_manifest_requires_sha256_input_hashes() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        AnalysisRunManifest(
            run_id="run-1", created_at=T, code_commit="abcdef1", account_snapshot_hash="bad",
            security_master_version="v1", allocator_identity="deterministic",
        )


def test_provider_health_bounds_retries() -> None:
    assert (
        ProviderHealth(
            provider="sec", status=ProviderHealthStatus.DEGRADED, checked_at=T, retries=2
        ).retries
        == 2
    )
    with pytest.raises(ValueError):
        ProviderHealth(
            provider="sec", status=ProviderHealthStatus.UNAVAILABLE, checked_at=T, retries=3
        )


def test_replay_safe_cache_preserves_original_availability_and_rejects_secrets(tmp_path) -> None:
    cache = ReplaySafeObservationCache(tmp_path / "observations.json")
    record = CachedObservation(
        cache_key="sec:aapl:filing", observation_type="sec_filing", provider="sec",
        schema_version="1", available_at=T, retrieved_at=T, source_hash=H,
        payload={"accession": "0000320193-25-000073"},
    )
    assert cache.put(record) == record
    assert cache.put(record.model_copy(update={"retrieved_at": T + timedelta(days=1)})) == record
    with pytest.raises(ValueError, match="AVAILABLE_AT_IMMUTABLE"):
        cache.put(record.model_copy(update={"available_at": T + timedelta(days=1)}))
    with pytest.raises(ValueError, match="SENSITIVE"):
        CachedObservation(
            cache_key="bad", observation_type="llm", provider="deepseek", schema_version="1",
            available_at=T, retrieved_at=T, source_hash=H, payload={"api_key": "secret"},
        )
