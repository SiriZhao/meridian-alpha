"""Optional FinRL-X shadow challenger; no vendor or execution imports."""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from meridian.schemas import AccountSnapshot, StableModel, TargetPortfolio


class ModelArtifactStatus(StrEnum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    DEVELOPMENT_MODEL = "DEVELOPMENT_MODEL"
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
    oos_metrics: dict[str, Decimal] = Field(min_length=1)
    walk_forward_status: str = Field(min_length=1, max_length=128)
    provenance: str = Field(min_length=1, max_length=1024)
    status: ModelArtifactStatus = ModelArtifactStatus.DEVELOPMENT_MODEL

    @model_validator(mode="after")
    def validate_cutoffs(self):
        if self.training_start > self.training_end or self.training_end > self.trained_at:
            raise ValueError("invalid model training chronology")
        if self.information_cutoff > self.training_end:
            raise ValueError("information cutoff cannot follow training end")
        return self


class ChallengerResult(StableModel):
    status: ModelArtifactStatus
    model_id: str | None = None
    proposed_target: TargetPortfolio | None = None
    uncertainty: Decimal | None = Field(default=None, ge=0, le=1)
    warnings: tuple[str, ...] = ()
    promotion_eligible: bool = False


class FinRLXAllocatorChallenger:
    """Shadow-only boundary. It does not import FinRL-X or execute inference."""

    def compare(
        self, account: AccountSnapshot, feature_snapshot_hash: str, manifest: ModelArtifactManifest | None
    ) -> ChallengerResult:
        _ = account
        if manifest is None:
            return ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE,
                                   warnings=("MODEL_UNAVAILABLE:manifest-required",))
        if manifest.status is not ModelArtifactStatus.VALIDATED_SHADOW:
            return ChallengerResult(status=manifest.status, model_id=manifest.model_id,
                                   warnings=("NON_PRODUCTION_NOT_PROMOTION_ELIGIBLE",))
        if not Path(manifest.artifact_path).is_file():
            return ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE, model_id=manifest.model_id,
                                   warnings=("MODEL_UNAVAILABLE:artifact-not-present",))
        _ = hashlib.sha256(feature_snapshot_hash.encode()).hexdigest()
        return ChallengerResult(status=ModelArtifactStatus.MODEL_UNAVAILABLE, model_id=manifest.model_id,
                               warnings=("MODEL_UNAVAILABLE:isolated-finrlx-runtime-not-installed",))