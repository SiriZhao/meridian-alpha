import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.challenger import (
    CallableShadowRuntime,
    ChallengerResult,
    FeatureSnapshot,
    FinRLXAllocatorChallenger,
    ModelArtifactManifest,
    ModelArtifactStatus,
)
from meridian.dislocation import (
    DislocationAssessment,
    DislocationScreen,
    DislocationStatus,
    bounded_modifier,
    certify_dislocation_assessment,
)
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    EvidenceItem,
    FreshnessState,
    TargetPortfolio,
    TargetPosition,
)

T = datetime(2026, 8, 30, tzinfo=UTC)


def account() -> AccountSnapshot:
    return AccountSnapshot(snapshot_id="synthetic", account_alias="fixture", provider="fixture", as_of=T,
        total_equity=Decimal("50000"), cash=Decimal("50000"), sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED)


def test_finrlx_challenger_requires_manifest_and_never_promotes() -> None:
    result = FinRLXAllocatorChallenger().compare(account(), "a" * 64, None)
    assert result.status is ModelArtifactStatus.MODEL_UNAVAILABLE
    assert result.promotion_eligible is False
    with pytest.raises(ValueError, match="HUMAN_REVIEW"):
        ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE, promotion_eligible=True)


def test_validated_shadow_boundary_receives_only_frozen_feature_snapshot(tmp_path) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"development artifact")
    import hashlib

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    h = hashlib.sha256(b"x").hexdigest()
    manifest = ModelArtifactManifest(
        model_id="dev-finrlx",
        model_type="DEVELOPMENT_MODEL",
        model_hash=digest,
        artifact_path=str(artifact),
        framework_version="unavailable",
        framework_commit="1234567",
        training_code_commit="7654321",
        trained_at=T,
        training_start=T - timedelta(days=30),
        training_end=T - timedelta(days=1),
        information_cutoff=T - timedelta(days=1),
        universe=("AAPL",),
        feature_schema="meridian.frozen.v1",
        feature_versions={"momentum": "v1"},
        target_objective="long_only",
        action_space="target_weights",
        random_seed=7,
        hyperparameter_hash=h,
        normalization_state_hash=h,
        transaction_cost_assumption=Decimal("0.001"),
        benchmark="SPY",
        oos_period="unavailable",
        oos_metrics={"status": Decimal("0")},
        walk_forward_status="NOT_RUN",
        provenance="development-only; no promotion",
        status=ModelArtifactStatus.VALIDATED_SHADOW,
    )
    feature = FeatureSnapshot(
        asset="AAPL", as_of=T, available_at=T, features={"momentum": Decimal("0.1")},
        source_hashes=(h,), feature_version="v1", normalization_version="n1",
    )
    seen = []

    def infer(request, received_manifest):
        seen.append((request.feature_snapshot.asset, request.account_snapshot_id, received_manifest.model_id))
        return ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE)

    result = FinRLXAllocatorChallenger(CallableShadowRuntime(infer)).shadow_infer(
        feature, account(), {"min_cash_weight": Decimal("0.1")}, manifest
    )
    assert result.status is ModelArtifactStatus.MODEL_UNAVAILABLE
    assert seen == [("AAPL", "synthetic", "dev-finrlx")]
    assert result.feature_snapshot_hash == feature.content_hash


def test_shadow_infer_rechecks_artifact_before_runtime(tmp_path) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"artifact")
    h = hashlib.sha256(b"x").hexdigest()
    manifest = ModelArtifactManifest(
        model_id="validated",
        model_type="shadow",
        model_hash=hashlib.sha256(b"different").hexdigest(),
        artifact_path=str(artifact),
        framework_version="1",
        framework_commit="1234567",
        training_code_commit="7654321",
        trained_at=T,
        training_start=T - timedelta(days=30),
        training_end=T - timedelta(days=1),
        information_cutoff=T - timedelta(days=1),
        universe=("AAPL",),
        feature_schema="meridian.frozen.v1",
        feature_versions={"momentum": "v1"},
        target_objective="long_only",
        action_space="target_weights",
        random_seed=1,
        hyperparameter_hash=h,
        normalization_state_hash=h,
        transaction_cost_assumption=Decimal("0.001"),
        benchmark="SPY",
        oos_period="unavailable",
        oos_metrics={"status": Decimal("0")},
        walk_forward_status="NOT_RUN",
        provenance="test",
        status=ModelArtifactStatus.VALIDATED_SHADOW,
    )
    feature = FeatureSnapshot(
        asset="AAPL", as_of=T, available_at=T, features={"momentum": Decimal("0.1")},
        source_hashes=(h,), feature_version="v1", normalization_version="n1",
    )
    called = False

    def infer(*_args):
        nonlocal called
        called = True
        return ChallengerResult(status=ModelArtifactStatus.VALIDATED_SHADOW)

    result = FinRLXAllocatorChallenger(CallableShadowRuntime(infer)).shadow_infer(
        feature, account(), {}, manifest
    )
    assert result.status is ModelArtifactStatus.MODEL_UNAVAILABLE
    assert "artifact-hash-mismatch" in result.warnings[0]
    assert called is False


def test_shadow_infer_rejects_target_policy_violation(tmp_path) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    h = hashlib.sha256(b"x").hexdigest()
    manifest = ModelArtifactManifest(
        model_id="validated",
        model_type="shadow",
        model_hash=digest,
        artifact_path=str(artifact),
        framework_version="1",
        framework_commit="1234567",
        training_code_commit="7654321",
        trained_at=T,
        training_start=T - timedelta(days=30),
        training_end=T - timedelta(days=1),
        information_cutoff=T - timedelta(days=1),
        universe=("AAPL",),
        feature_schema="meridian.frozen.v1",
        feature_versions={"momentum": "v1"},
        target_objective="long_only",
        action_space="target_weights",
        random_seed=1,
        hyperparameter_hash=h,
        normalization_state_hash=h,
        transaction_cost_assumption=Decimal("0.001"),
        benchmark="SPY",
        oos_period="unavailable",
        oos_metrics={"status": Decimal("0")},
        walk_forward_status="NOT_RUN",
        provenance="test",
        status=ModelArtifactStatus.VALIDATED_SHADOW,
    )
    feature = FeatureSnapshot(
        asset="AAPL", as_of=T, available_at=T, features={"momentum": Decimal("0.1")},
        source_hashes=(h,), feature_version="v1", normalization_version="n1",
    )
    target = TargetPortfolio(
        as_of=T, cash_weight=Decimal("0.1"),
        positions=(
            TargetPosition(
                ticker="AAPL", target_weight=Decimal("0.9"), conviction=Decimal("0.5"),
                rationale="test",
            ),
        ),
        allocator_name="challenger", allocator_version="1",
    )
    result = FinRLXAllocatorChallenger(
        CallableShadowRuntime(lambda *_: ChallengerResult(
            status=ModelArtifactStatus.VALIDATED_SHADOW, proposed_target=target,
        ))
    ).shadow_infer(feature, account(), {"max_position_weight": Decimal("0.25")}, manifest)
    assert result.status is ModelArtifactStatus.MODEL_UNAVAILABLE
    assert "target_policy_violation" in result.warnings[0]


def test_allocator_comparison_does_not_fabricate_oos_metrics() -> None:
    from meridian.challenger import compare_target_portfolios

    deterministic = TargetPortfolio(
        as_of=T, cash_weight=Decimal("1"), positions=(),
        allocator_name="deterministic", allocator_version="1",
    )
    comparison = compare_target_portfolios(deterministic, None)
    assert comparison.status == "MODEL_UNAVAILABLE"
    assert comparison.return_oos is None
    assert comparison.benchmark_relative_return_oos is None


def test_dislocation_screen_is_bounded_and_deterministic() -> None:
    selected = DislocationScreen().select({
        "AAPL": {"drawdown": Decimal("-0.20"), "momentum_reversal": Decimal("0.2")},
        "MSFT": {"drawdown": Decimal("-0.05"), "momentum_reversal": Decimal("0.9")},
        "NVDA": {"drawdown": Decimal("-0.30"), "momentum_reversal": Decimal("0.1")},
    })
    assert tuple(item.ticker for item in selected) == ("NVDA", "AAPL")


def test_dislocation_modifier_requires_sealed_certified_evidence_view() -> None:
    from meridian.evidence import ProviderCapabilities
    from meridian.research import CertifiedEvidenceView, ResearchContextPacket
    from meridian.schemas import EvidencePointInTimeStatus

    evidence = EvidenceItem(ticker="AAPL", provider="sec", source="SEC:filing", observed_at=T,
        available_at=T, evidence_type="event", point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    assessment = DislocationAssessment(ticker="AAPL", status=DislocationStatus.AVAILABLE,
        stance="BULLISH", dislocation_conviction=Decimal("1"), cited_evidence_ids=(evidence.stable_id,))
    view = CertifiedEvidenceView.from_context(ResearchContextPacket(context_id="c", ticker="AAPL", as_of=T,
        created_at=T, items=(evidence,)), provider_registry={"sec": ProviderCapabilities(provider_name="sec",
        supports_historical=True, supports_point_in_time=True, research_grade=True)}, clock=lambda: T)
    certified = certify_dislocation_assessment(assessment, view)
    assert bounded_modifier(certified) == Decimal("0.10")
    with pytest.raises(ValueError, match="exact CertifiedEvidenceView"):
        certify_dislocation_assessment(assessment.model_copy(update={"cited_evidence_ids": ("unknown",)}), view)

def test_raw_dislocation_assessment_cannot_authorize_modifier() -> None:
    raw = DislocationAssessment(ticker="AAPL", status=DislocationStatus.AVAILABLE,
        stance="BULLISH", dislocation_conviction=Decimal("1"), cited_evidence_ids=("not-enough",))
    with pytest.raises(TypeError, match="CertifiedDislocationAssessment"):
        bounded_modifier(raw)  # type: ignore[arg-type]
