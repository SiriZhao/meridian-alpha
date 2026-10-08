"""Versioned, predeclared research parameters, never fitted to final OOS."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from meridian.quant.numerics import deterministic_decimal
from meridian.schemas import StableModel


class QuantPolicy(StableModel):
    version: Literal["quant-v2.1"] = "quant-v2.1"
    mode: Literal["QUANT_V1_BASELINE", "QUANT_V2_SHADOW", "QUANT_V2_PAPER_CANDIDATE"] = "QUANT_V1_BASELINE"
    strategy: Literal["A0", "A1", "A2", "A3", "A4"] = "A4"
    paper_approved: bool = False
    approval_reference: str | None = None
    momentum_weight: Decimal = Field(default=Decimal("0.7"), ge=0, le=1)
    trend_weight: Decimal = Field(default=Decimal("0.3"), ge=0, le=1)
    cross_section_minimum: int = Field(default=5, ge=3)
    momentum_scale: Decimal = Field(default=Decimal("0.10"), gt=0)
    trend_scale: Decimal = Field(default=Decimal("0.05"), gt=0)
    volatility_floor: Decimal = Field(default=Decimal("0.05"), gt=0)
    target_volatility: Decimal = Field(default=Decimal("0.15"), gt=0, le=1)
    minimum_dollar_volume: Decimal = Field(default=Decimal("1000000"), gt=0)
    max_volume_participation: Decimal = Field(default=Decimal("0.01"), gt=0, le=1)
    allocation: Literal["score", "inverse_volatility", "risk_adjusted"] = "risk_adjusted"
    regime_trend_band: Decimal = Field(default=Decimal("0.02"), gt=0, le=1)
    high_volatility_percentile: Decimal = Field(default=Decimal("0.80"), gt=0, le=1)
    high_volatility_absolute: Decimal = Field(default=Decimal("0.25"), gt=0)
    risk_off_drawdown: Decimal = Field(default=Decimal("-0.15"), gt=-1, lt=0)
    high_volatility_multiplier: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    downtrend_multiplier: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    rebalance: Literal["daily", "weekly", "threshold"] = "threshold"
    no_trade_band: Decimal = Field(default=Decimal("0.01"), ge=0, le=1)
    rebalance_threshold: Decimal = Field(default=Decimal("0.02"), ge=0, le=2)
    minimum_trade_notional: Decimal = Field(default=Decimal("100"), ge=0)
    max_turnover: Decimal = Field(default=Decimal("0.20"), gt=0, le=2)
    minimum_benefit_cost_ratio: Decimal = Field(default=Decimal("1.5"), ge=1)
    minimum_oos_sessions: int = Field(default=252, ge=252)
    minimum_oos_folds: int = Field(default=2, ge=2)
    correlation_limit: Decimal | None = Field(default=None, gt=0, le=1)
    correlation_lookback: int = Field(default=60, ge=20)
    # Prices are never an expected return forecast. Benefit gating is only used
    # when a separately calibrated, PIT estimate is explicitly supplied.
    use_momentum: bool = True
    use_trend: bool = True
    use_volatility_adjustment: bool = True
    use_cost_gate: bool = True

    @model_validator(mode="after")
    @deterministic_decimal
    def coherent(self) -> "QuantPolicy":
        if self.momentum_weight + self.trend_weight != 1:
            raise ValueError("QUANT_GROUP_WEIGHTS_MUST_SUM_TO_ONE")
        if self.mode == "QUANT_V2_PAPER_CANDIDATE" and (
            not self.paper_approved or not self.approval_reference
        ):
            raise ValueError("QUANT_PAPER_HUMAN_APPROVAL_REQUIRED")
        return self


class CostPolicy(StableModel):
    version: Literal["quant-cost-v1"] = "quant-cost-v1"
    commission_per_order: Decimal = Field(default=Decimal("1"), ge=0)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0, le=1000)
    # None is unknown; do not claim an observed spread or add a fictitious one.
    spread_bps: Decimal | None = Field(default=None, ge=0, le=1000)

    @property
    @deterministic_decimal
    def adverse_fraction(self) -> Decimal:
        return (self.slippage_bps + (self.spread_bps or Decimal(0)) / 2) / 10000

    @deterministic_decimal
    def estimate(self, notional: Decimal, order_count: int) -> Decimal:
        if not notional.is_finite() or notional < 0 or order_count < 0:
            raise ValueError("NEGATIVE_COST_INPUT")
        return notional * self.adverse_fraction + order_count * self.commission_per_order


def load_quant_policy(path: Path) -> QuantPolicy:
    return QuantPolicy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
