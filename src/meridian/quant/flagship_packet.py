"""Opt-in V2.3 research snapshot for qualified inputs; never a paper switch."""
import hashlib
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Literal

from meridian.config import RiskPolicy
from meridian.historical import HistoricalBarSeries
from meridian.quant.backtest import pit_correlations
from meridian.quant.features import ChallengerFeatureSnapshot, compute_challenger_features
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.flagship_portfolio import FlagshipAllocation, construct_flagship
from meridian.quant.flagship_replay import flagship_engine_hash
from meridian.quant.policy import CostPolicy
from meridian.quant.portfolio import RebalanceDecision, challenger_rebalance
from meridian.quant.regime import RegimeState, detect_regime
from meridian.quant.signals import ChallengerScore, score_challenger
from meridian.schemas import StableModel


class FlagshipResearchPacket(StableModel):
    version: Literal['quant-research-v2.3'] = 'quant-research-v2.3'
    authority: Literal['SHADOW_ONLY'] = 'SHADOW_ONLY'
    cutoff: datetime
    engine_hash: str
    history_hashes: dict[str, str]
    features: tuple[ChallengerFeatureSnapshot, ...]
    scores: tuple[ChallengerScore, ...]
    regime: RegimeState
    allocation: FlagshipAllocation
    cost_adjusted_proposal: RebalanceDecision
    evidence_level: Literal['CERTIFIED_PIT', 'SYNTHETIC_DIAGNOSTIC']
    expected_return: None = None
    predictive_confidence: None = None
    authorized_trade: Literal[False] = False
    unknowns: tuple[str, ...] = ('CALIBRATED_EXPECTED_RETURN', 'OBSERVED_SPREAD', 'ETF_LOOKTHROUGH', 'FUNDAMENTAL_PIT', 'ACTUAL_FILL_STATE')

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


def build_flagship_packet(histories: Mapping[str, HistoricalBarSeries], cutoff: datetime, *,
                          symbols: tuple[str, ...], current: Mapping[str, Decimal], nav: Decimal,
                          risk: RiskPolicy, policy: FlagshipPolicy, costs: CostPolicy,
                          sector_map: Mapping[str, str | None], asset_types: Mapping[str, str],
                          diagnostic: bool = False, prior: Mapping[str, ChallengerScore] | None = None) -> FlagshipResearchPacket:
    if 'SPY' not in histories or len(set(symbols)) != len(symbols) or 'SPY' in symbols or len(symbols) > policy.maximum_symbols:
        raise ValueError('V23_PACKET_BENCHMARK_OR_UNIVERSE_INVALID')
    if any(s not in histories or histories[s].canonical_symbol != s for s in (*symbols, 'SPY')):
        raise ValueError('V23_PACKET_HISTORY_IDENTITY_INVALID')
    extended = {s: compute_challenger_features(histories[s], cutoff, benchmark=histories['SPY'], diagnostic=diagnostic) for s in (*symbols, 'SPY')}
    if any(f.base.quality_status == 'REJECTED' for f in extended.values()):
        raise ValueError('V23_PACKET_HISTORY_QUALITY_REJECTED')
    regime = detect_regime(extended['SPY'].base, policy.baseline.controls)
    scores = score_challenger([extended[s] for s in symbols], policy.baseline, regime, prior=prior)
    features = {s: f.base for s, f in extended.items()}
    allocation = construct_flagship(scores, features, cutoff, risk, policy, regime,
        current=current, correlations=pit_correlations({s: histories[s] for s in symbols}, cutoff, policy.baseline.controls.correlation_lookback),
        sector_map=sector_map, asset_types=asset_types, extended=extended, costs=costs, nav=nav, diagnostic=diagnostic)
    proposal = challenger_rebalance(allocation.allocation, current, nav=nav, risk=risk, policy=policy.baseline,
        costs=costs, dollar_volumes={s: f.value('dollar_volume_20') for s, f in features.items()})
    return FlagshipResearchPacket(cutoff=cutoff, engine_hash=flagship_engine_hash(),
        history_hashes={s: histories[s].stable_hash for s in sorted(extended)},
        features=tuple(extended[s] for s in sorted(extended)), scores=tuple(scores), regime=regime,
        allocation=allocation, cost_adjusted_proposal=proposal,
        evidence_level='SYNTHETIC_DIAGNOSTIC' if any(f.base.synthetic for f in extended.values()) else 'CERTIFIED_PIT')
