"""Deterministic risk overlay; LLMs are deliberately absent."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from meridian.config import RiskPolicy
from meridian.schemas import AccountSnapshot, TargetPortfolio
from meridian.security import AssetType, SecurityMetadata


@dataclass(frozen=True)
class RiskReport:
    original: TargetPortfolio
    approved: TargetPortfolio
    violations: tuple[str, ...]
    modifications: tuple[str, ...]


class RiskEngine:
    def approve(
        self,
        target: TargetPortfolio,
        account: AccountSnapshot,
        regime: str,
        policy: RiskPolicy,
        sectors: dict[str, str] | None = None,
        metadata: dict[str, SecurityMetadata] | None = None,
    ) -> RiskReport:
        sectors = sectors or {}
        metadata = metadata or {}
        violations = []
        modifications = []
        used_sector = {}
        positions = []
        for position in sorted(
            target.positions, key=lambda item: (-item.target_weight, item.ticker)
        )[: policy.max_number_positions]:
            meta = metadata.get(position.ticker)
            if (
                policy.max_sector_weight < Decimal("1")
                and meta is None
                and position.ticker not in sectors
            ):
                violations.append(f"{position.ticker}: missing security metadata")
                continue
            if (
                meta is not None
                and meta.asset_type is AssetType.EQUITY
                and policy.max_sector_weight < Decimal("1")
                and not meta.sector
            ):
                violations.append(f"{position.ticker}: missing sector metadata")
                continue
            weight = min(position.target_weight, policy.max_position_weight)
            if weight != position.target_weight:
                violations.append(f"{position.ticker}: max_position_weight")
                modifications.append(f"capped {position.ticker} at max position weight")
            sector = meta.sector if meta is not None else sectors.get(position.ticker)
            if sector is not None:
                capacity = policy.max_sector_weight - used_sector.get(sector, Decimal("0"))
                if capacity <= 0:
                    violations.append(f"{position.ticker}: max_sector_weight")
                    continue
                if weight > capacity:
                    weight = capacity
                    violations.append(f"{position.ticker}: max_sector_weight")
            if regime == "RISK_OFF":
                reduced = weight / Decimal("2")
                if reduced != weight:
                    modifications.append(f"risk-off reduction for {position.ticker}")
                weight = reduced
            if weight > 0:
                positions.append(position.model_copy(update={"target_weight": weight}))
                if sector is not None:
                    used_sector[sector] = used_sector.get(sector, Decimal("0")) + weight
        invested = sum((p.target_weight for p in positions), Decimal("0"))
        capacity = Decimal("1") - policy.min_cash_weight
        if invested > capacity:
            scale = capacity / invested
            positions = [
                p.model_copy(update={"target_weight": p.target_weight * scale}) for p in positions
            ]
            invested = capacity
            violations.append("min_cash_weight")
            modifications.append("scaled positions to preserve cash floor")
        approved = TargetPortfolio(
            as_of=target.as_of,
            cash_weight=Decimal("1") - invested,
            positions=tuple(positions),
            allocator_name=target.allocator_name,
            allocator_version=target.allocator_version,
        )
        return RiskReport(target, approved, tuple(violations), tuple(modifications))
