"""V2.3 predeclared shadow-only research controls; no forecast or paper switch."""
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from meridian.quant.policy import ChallengerPolicy
from meridian.schemas import StableModel


class FlagshipPolicy(StableModel):
    version: Literal["quant-v2.3"] = "quant-v2.3"
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    baseline: ChallengerPolicy = Field(default_factory=ChallengerPolicy)
    construction: Literal["V22_BASELINE", "INVERSE_VOLATILITY", "SHRUNK_RISK_BUDGET", "COST_CONSTRAINED", "REGIME_CONDITIONED"] = "COST_CONSTRAINED"
    preference_weight: Decimal = Field(default=Decimal("1"), gt=0, le=10, allow_inf_nan=False)
    risk_weight: Decimal = Field(default=Decimal("0.10"), ge=0, le=1, allow_inf_nan=False)
    turnover_weight: Decimal = Field(default=Decimal("0.02"), ge=0, le=1, allow_inf_nan=False)
    cost_weight: Decimal = Field(default=Decimal("1"), ge=0, le=10, allow_inf_nan=False)
    # Small deterministic grid, not an unconstrained solver or fitted return model.
    step_sizes: tuple[Decimal, ...] = (Decimal(".02"), Decimal(".01"), Decimal(".005"))
    sweeps_per_step: int = Field(default=2, ge=1, le=8)
    maximum_symbols: int = Field(default=8, ge=1, le=8)
    downside_budget: Decimal = Field(default=Decimal(".10"), gt=0, le=Decimal(".15"), allow_inf_nan=False)
    beta_budget: Decimal = Field(default=Decimal(".60"), gt=0, le=1, allow_inf_nan=False)
    instability_ceiling: Decimal = Field(default=Decimal(".50"), gt=0, le=1, allow_inf_nan=False)
    expected_return_calibration: Literal["EXPECTED_RETURN_UNCALIBRATED"] = "EXPECTED_RETURN_UNCALIBRATED"

    @model_validator(mode="after")
    def bounded_grid(self) -> "FlagshipPolicy":
        if (self.baseline.controls.target_volatility > Decimal('.15') or self.baseline.cluster_weight_cap > Decimal('.40')
                or self.baseline.unknown_correlation_exposure > Decimal('.25')
                or self.baseline.controls.max_turnover > Decimal('.20')
                or self.baseline.controls.max_volume_participation > Decimal('.01')
                or not self.baseline.controls.use_cost_gate):
            raise ValueError('V23_BASELINE_RISK_CEILING_MUST_NOT_WEAKEN')
        if not 1 <= len(self.step_sizes) <= 4 or any(not x.is_finite() or not 0 < x <= Decimal('.05') for x in self.step_sizes):
            raise ValueError("V23_INVALID_GRID")
        if any(a <= b for a, b in zip(self.step_sizes, self.step_sizes[1:], strict=False)):
            raise ValueError("V23_GRID_MUST_DESCEND")
        return self

    @property
    def digest(self) -> str:
        import hashlib
        return hashlib.sha256(self.stable_json().encode()).hexdigest()
