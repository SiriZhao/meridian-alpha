"""Optional FinRL-X shadow challenger; no vendor or execution imports."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import Field, model_validator

from meridian.reproducibility import FrozenFeature
from meridian.schemas import AccountSnapshot, StableModel, TargetPortfolio

FeatureSnapshot = FrozenFeature


class ModelArtifactStatus(StrEnum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_INVALID = "MODEL_INVALID"
    DEVELOPMENT_MODEL = "DEVELOPMENT_MODEL"
    ARTIFACT_VALIDATED = "ARTIFACT_VALIDATED"
    OOS_VALIDATED_SHADOW = "OOS_VALIDATED_SHADOW"
    PROMOTION_ELIGIBLE = "PROMOTION_ELIGIBLE"
    # Kept as a compatibility value for pre-5F fixtures.  It is deliberately
    # never treated as OOS validation or promotion eligibility.
    VALIDATED_SHADOW = "VALIDATED_SHADOW"


class ModelArtifactManifest(StableModel):
    model_id: str = Field(min_length=1, max_length=128)
    model_type: str = Field(min_length=1, max_length=128)
    model_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_path: str = Field(min_length=1, max_length=1024)
    framework_version: str = Field(min_length=1, max_length=128)
    framework_commit: str = Field(min_length=7, max_length=64)
    training_code_commit: str = Field(min_length=7, max_length=64)
    trained_at: datetime
    training_start: datetime
    training_end: datetime
    information_cutoff: datetime
    universe: tuple[str, ...] = Field(min_length=1, max_length=500)
    feature_schema: str = Field(min_length=1, max_length=128)
    feature_versions: dict[str, str] = Field(min_length=1)
    target_objective: str = Field(min_length=1, max_length=256)
    action_space: str = Field(min_length=1, max_length=256)
    random_seed: int
    hyperparameter_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalization_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    transaction_cost_assumption: Decimal = Field(ge=0, le=1)
    benchmark: str = Field(min_length=1, max_length=64)
    oos_period: str = Field(min_length=1, max_length=128)
    oos_metrics: dict[str, Decimal | str] = Field(min_length=1)
    walk_forward_status: str = Field(min_length=1, max_length=128)
    validation_period: str = Field(default="not_run", min_length=1, max_length=128)
    walk_forward_result: dict[str, Decimal | str] = Field(default_factory=dict)
    provenance: str = Field(min_length=1, max_length=1024)
    status: ModelArtifactStatus = ModelArtifactStatus.DEVELOPMENT_MODEL

    @model_validator(mode="before")
    @classmethod
    def accept_canonical_artifact_hash(cls, data):
        if isinstance(data, dict) and "model_hash" not in data and "artifact_hash" in data:
            data = dict(data)
            data["model_hash"] = data.pop("artifact_hash")
        return data

    @model_validator(mode="after")
    def validate_cutoffs(self):
        if self.training_start > self.training_end or self.training_end > self.trained_at:
            raise ValueError("invalid model training chronology")
        if self.information_cutoff > self.training_end:
            raise ValueError("information cutoff cannot follow training end")
        if self.status is ModelArtifactStatus.OOS_VALIDATED_SHADOW:
            fields: tuple[tuple[str, object], ...] = (
                ("framework_version", self.framework_version),
                ("framework_commit", self.framework_commit),
                ("training_code_commit", self.training_code_commit),
                ("training_period", f"{self.training_start.isoformat()}/{self.training_end.isoformat()}"),
                ("validation_period", self.validation_period),
                ("oos_period", self.oos_period),
                ("benchmark", self.benchmark),
                ("feature_schema", self.feature_schema),
                ("normalization", self.normalization_state_hash),
                ("objective", self.target_objective),
                ("action_space", self.action_space),
                ("walk_forward_status", self.walk_forward_status),
            )
            placeholders = {"", "unavailable", "not_run", "none", "unknown", "n/a"}
            for name, value in fields:
                if str(value).strip().casefold() in placeholders:
                    raise ValueError(f"OOS_VALIDATION_MISSING:{name}")
            if not self.oos_metrics or not self.walk_forward_result:
                raise ValueError("OOS_VALIDATION_MISSING:metrics-or-walk-forward")
            for label, values in (("oos_metrics", self.oos_metrics), ("walk_forward_result", self.walk_forward_result)):
                if any(str(value).strip().casefold() in placeholders for value in values.values()):
                    raise ValueError(f"OOS_VALIDATION_MISSING:{label}")
        return self

    @property
    def artifact_hash(self) -> str:
        """Canonical name used by the 5F contract (``model_hash`` is legacy)."""

        return self.model_hash

    @property
    def oos_validated(self) -> bool:
        return self.status is ModelArtifactStatus.OOS_VALIDATED_SHADOW


class ChallengerResult(StableModel):
    status: ModelArtifactStatus
    model_id: str | None = None
    proposed_target: TargetPortfolio | None = None
    uncertainty: Decimal | None = Field(default=None, ge=0, le=1)
    warnings: tuple[str, ...] = ()
    promotion_eligible: bool = False
    feature_snapshot_hash: str | None = None
    artifact_hash: str | None = None
    runtime: str = "isolated-finrlx-unavailable"

    @model_validator(mode="after")
    def no_automatic_promotion(self) -> ChallengerResult:
        if self.promotion_eligible:
            raise ValueError("FINRLX_PROMOTION_REQUIRES_HUMAN_REVIEW")
        return self


class FinRLXInferenceRequest(StableModel):
    """Minimal, sanitized input crossing the optional challenger boundary."""

    feature_snapshot: FeatureSnapshot
    account_snapshot_id: str = Field(min_length=1, max_length=128)
    account_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_constraints: dict[str, Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sanitized_account_identity(self) -> FinRLXInferenceRequest:
        if re.search(r"(?i)(account[_-]?(number|id)|token|credential|password)", self.account_snapshot_id):
            raise ValueError("FINRLX_SANITIZED_ACCOUNT_ID_REQUIRED")
        return self


class FinRLXRuntime(Protocol):
    """Optional runtime protocol; implementations must be side-effect free."""

    name: str

    def infer(
        self, request: FinRLXInferenceRequest, manifest: ModelArtifactManifest
    ) -> ChallengerResult: ...


class UnavailableFinRLXRuntime:
    name = "MODEL_UNAVAILABLE"

    def infer(
        self, request: FinRLXInferenceRequest, manifest: ModelArtifactManifest
    ) -> ChallengerResult:
        return ChallengerResult(
            status=ModelArtifactStatus.MODEL_UNAVAILABLE,
            model_id=manifest.model_id,
            artifact_hash=manifest.model_hash,
            feature_snapshot_hash=request.feature_snapshot.content_hash,
            runtime=self.name,
            warnings=("MODEL_UNAVAILABLE:isolated-finrlx-runtime-not-installed",),
        )


class CallableShadowRuntime:
    """Test/development runtime adapter with no vendor or execution imports.

    Production code may inject a separately reviewed, side-effect-free
    callable.  The callable receives only ``FinRLXInferenceRequest`` and the
    validated manifest and can return proposed weights, never orders.
    """

    name = "isolated-finrlx-shadow"
    fixture_compatibility = True

    def __init__(
        self,
        infer_fn: Callable[[FinRLXInferenceRequest, ModelArtifactManifest], ChallengerResult],
    ) -> None:
        self._infer_fn = infer_fn

    def infer(
        self, request: FinRLXInferenceRequest, manifest: ModelArtifactManifest
    ) -> ChallengerResult:
        result = self._infer_fn(request, manifest)
        if not isinstance(result, ChallengerResult):
            raise TypeError("FinRL-X runtime must return ChallengerResult")
        if result.proposed_target is not None and result.model_id not in {None, manifest.model_id}:
            raise ValueError("FinRL-X runtime returned a mismatched model identity")
        return result.model_copy(
            update={
                "model_id": result.model_id or manifest.model_id,
                "artifact_hash": manifest.model_hash,
                "feature_snapshot_hash": request.feature_snapshot.content_hash,
                "runtime": self.name,
            }
        )


class AllocatorComparison(StableModel):
    """Read-only comparison of target portfolios; missing OOS data stays null."""

    status: str
    deterministic_weights: dict[str, Decimal]
    challenger_weights: dict[str, Decimal] = Field(default_factory=dict)
    deterministic_cash: Decimal
    challenger_cash: Decimal | None = None
    concentration_deterministic: Decimal
    concentration_challenger: Decimal | None = None
    cash_delta: Decimal | None = None
    turnover_proxy: Decimal | None = None
    stability_l1: Decimal | None = None
    return_oos: Decimal | None = None
    benchmark_relative_return_oos: Decimal | None = None
    volatility_oos: Decimal | None = None
    sharpe_oos: Decimal | None = None
    max_drawdown_oos: Decimal | None = None
    transaction_cost_oos: Decimal | None = None
    tail_behavior_oos: str | None = None


def compare_target_portfolios(
    deterministic: TargetPortfolio, challenger: TargetPortfolio | None
) -> AllocatorComparison:
    """Compare proposals without inventing backtest/OOS performance."""
    base = {item.ticker: item.target_weight for item in deterministic.positions}
    challenger_weights = (
        {item.ticker: item.target_weight for item in challenger.positions}
        if challenger is not None
        else {}
    )
    if challenger is None:
        return AllocatorComparison(
            status="MODEL_UNAVAILABLE", deterministic_weights=base,
            deterministic_cash=deterministic.cash_weight,
            concentration_deterministic=max(base.values(), default=Decimal("0")),
        )
    universe = set(base) | set(challenger_weights)
    stability = sum(
        (
            abs(base.get(key, Decimal("0")) - challenger_weights.get(key, Decimal("0")))
            for key in universe
        ),
        Decimal("0"),
    ) + abs(deterministic.cash_weight - challenger.cash_weight)
    return AllocatorComparison(
        status="SHADOW_COMPARISON_ONLY", deterministic_weights=base,
        challenger_weights=challenger_weights, deterministic_cash=deterministic.cash_weight,
        challenger_cash=challenger.cash_weight,
        concentration_deterministic=max(base.values(), default=Decimal("0")),
        concentration_challenger=max(challenger_weights.values(), default=Decimal("0")),
        cash_delta=abs(deterministic.cash_weight - challenger.cash_weight),
        turnover_proxy=stability / Decimal("2"), stability_l1=stability,
    )


class FinRLXAllocatorChallenger:
    """Shadow-only boundary. It does not import FinRL-X or execute inference."""

    def __init__(self, runtime: FinRLXRuntime | None = None) -> None:
        self.runtime = runtime or UnavailableFinRLXRuntime()

    def compare(
        self, account: AccountSnapshot, feature_snapshot_hash: str, manifest: ModelArtifactManifest | None
    ) -> ChallengerResult:
        _ = account
        if manifest is None:
            return ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                                   feature_snapshot_hash=feature_snapshot_hash,
                                   warnings=("MODEL_UNAVAILABLE:manifest-required",))
        if manifest.status not in {
            ModelArtifactStatus.OOS_VALIDATED_SHADOW,
        }:
            return ChallengerResult(status=manifest.status, model_id=manifest.model_id,
                                   feature_snapshot_hash=feature_snapshot_hash,
                                   warnings=("NON_PRODUCTION_NOT_PROMOTION_ELIGIBLE",))
        artifact_error, digest = _artifact_status(manifest)
        if artifact_error is not None:
            return ChallengerResult(
                status=(ModelArtifactStatus.MODEL_INVALID
                        if manifest.oos_validated else ModelArtifactStatus.MODEL_UNAVAILABLE),
                model_id=manifest.model_id,
                feature_snapshot_hash=feature_snapshot_hash,
                artifact_hash=digest,
                warnings=(artifact_error,),
            )
        return ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE, model_id=manifest.model_id,
                               feature_snapshot_hash=feature_snapshot_hash,
                               artifact_hash=manifest.model_hash,
                               runtime=self.runtime.name,
                               warnings=("MODEL_UNAVAILABLE:isolated-finrlx-runtime-not-installed",))

    def shadow_infer(
        self,
        feature_snapshot: FeatureSnapshot,
        account: AccountSnapshot,
        policy_constraints: dict[str, Decimal],
        manifest: ModelArtifactManifest | None,
    ) -> ChallengerResult:
        """Run an optional isolated runtime; default is fail-closed."""
        legacy_fixture = (
            manifest is not None
            and manifest.status is ModelArtifactStatus.VALIDATED_SHADOW
            and getattr(self.runtime, "fixture_compatibility", False) is True
        )
        if manifest is None or (
            manifest.status is not ModelArtifactStatus.OOS_VALIDATED_SHADOW
            and not legacy_fixture
        ):
            return ChallengerResult(
                status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                feature_snapshot_hash=feature_snapshot.content_hash,
                warnings=("MODEL_UNAVAILABLE:validated-manifest-required",),
            )
        if feature_snapshot.asset not in manifest.universe:
            return ChallengerResult(
                status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                model_id=manifest.model_id,
                feature_snapshot_hash=feature_snapshot.content_hash,
                warnings=("MODEL_UNAVAILABLE:feature-universe-mismatch",),
            )
        artifact_error, digest = _artifact_status(manifest)
        if artifact_error is not None:
            return ChallengerResult(
                status=(ModelArtifactStatus.MODEL_INVALID
                        if manifest.oos_validated else ModelArtifactStatus.MODEL_UNAVAILABLE),
                model_id=manifest.model_id,
                feature_snapshot_hash=feature_snapshot.content_hash,
                artifact_hash=digest,
                warnings=(artifact_error,),
            )
        request = FinRLXInferenceRequest(
            feature_snapshot=feature_snapshot,
            account_snapshot_id=account.snapshot_id,
            account_state_hash=hashlib.sha256(account.stable_json().encode()).hexdigest(),
            policy_constraints=policy_constraints,
        )
        try:
            result = self.runtime.infer(request, manifest)
        except Exception as error:  # noqa: BLE001 - optional runtime is isolated
            return ChallengerResult(
                status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                model_id=manifest.model_id,
                feature_snapshot_hash=feature_snapshot.content_hash,
                artifact_hash=digest,
                runtime=self.runtime.name,
                warnings=(f"MODEL_UNAVAILABLE:runtime_error:{type(error).__name__}",),
            )
        if not isinstance(result, ChallengerResult):
            return ChallengerResult(
                status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                model_id=manifest.model_id,
                feature_snapshot_hash=feature_snapshot.content_hash,
                artifact_hash=digest,
                runtime=self.runtime.name,
                warnings=("MODEL_UNAVAILABLE:runtime_contract_violation",),
            )
        if result.proposed_target is not None:
            try:
                _validate_proposed_target(
                    result.proposed_target, feature_snapshot, manifest, policy_constraints
                )
            except ValueError as error:
                return ChallengerResult(
                    status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                    model_id=manifest.model_id,
                    feature_snapshot_hash=feature_snapshot.content_hash,
                    artifact_hash=digest,
                    runtime=self.runtime.name,
                    warnings=(f"MODEL_UNAVAILABLE:target_policy_violation:{error}",),
                )
        # Promotion is a separate human-reviewed gate and can never be asserted
        # by an injected runtime response.
        return result.model_copy(
            update={
                "model_id": result.model_id or manifest.model_id,
                "artifact_hash": manifest.model_hash,
                "feature_snapshot_hash": feature_snapshot.content_hash,
                "runtime": self.runtime.name,
                "promotion_eligible": False,
            }
        )


def _artifact_status(manifest: ModelArtifactManifest) -> tuple[str | None, str | None]:
    """Validate artifact presence and bytes immediately before any inference."""
    path = Path(manifest.artifact_path)
    if not path.is_file():
        return "MODEL_INVALID:artifact-not-present", None
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "MODEL_INVALID:artifact-read-failed", None
    if digest != manifest.model_hash:
        return "MODEL_INVALID:artifact-hash-mismatch", digest
    return None, digest


def _validate_proposed_target(
    target: TargetPortfolio,
    feature_snapshot: FeatureSnapshot,
    manifest: ModelArtifactManifest,
    policy_constraints: dict[str, Decimal],
) -> None:
    """Keep an optional challenger inside Meridian's allocator constraints."""
    if target.as_of != feature_snapshot.as_of:
        raise ValueError("FinRL-X target as_of does not match frozen feature cutoff")
    allowed = set(manifest.universe)
    if any(position.ticker not in allowed for position in target.positions):
        raise ValueError("FinRL-X target contains a ticker outside the validated universe")
    min_cash = policy_constraints.get("min_cash_weight")
    if min_cash is not None and target.cash_weight < min_cash:
        raise ValueError("FinRL-X target violates min_cash_weight")
    max_position = policy_constraints.get("max_position_weight")
    if max_position is not None and any(
        position.target_weight > max_position for position in target.positions
    ):
        raise ValueError("FinRL-X target violates max_position_weight")
