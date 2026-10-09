"""V2.3 signal hook; the existing next-open, cash and fill engine is unchanged."""
import hashlib
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path

from meridian.config import RiskPolicy
from meridian.quant.backtest import (
    QuantDataset,
    ReplayResult,
    WalkForwardFold,
    WalkForwardRunner,
    pit_correlations,
)
from meridian.quant.features import FeatureSnapshot
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.flagship_portfolio import construct_flagship
from meridian.quant.policy import ChallengerPolicy, CostPolicy, QuantPolicy
from meridian.quant.portfolio import challenger_rebalance, weights
from meridian.quant.regime import detect_regime
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.risk import RiskEngine
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState
from meridian.security import AssetType, SecurityMetadata
from meridian.trading_calendar import session_close


def flagship_engine_hash() -> str:
    root = Path(__file__).parent
    digest = hashlib.sha256(ENGINE_SOURCE_HASH.encode())
    for name in ('flagship_policy.py', 'flagship_portfolio.py', 'flagship_replay.py'):
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


class FlagshipWalkForwardRunner(WalkForwardRunner):
    def __init__(self, dataset: QuantDataset, flagship: FlagshipPolicy, *, diagnostic: bool = False) -> None:
        super().__init__(dataset, diagnostic=diagnostic)
        self.flagship = FlagshipPolicy.model_validate(flagship.model_dump())

    def run_flagship(self, costs: CostPolicy, risk: RiskPolicy, fold: WalkForwardFold,
                     *, partition: str = 'test') -> ReplayResult:
        if partition not in {'test', 'validation'}:
            raise ValueError('V23_PARTITION_INVALID')
        result = super().run(self.flagship.baseline.controls, costs, risk, fold,
            partition='test' if partition == 'test' else 'validation', strategy='V22', challenger=self.flagship.baseline)
        return result.model_copy(update={'strategy': 'V23_' + self.flagship.construction,
            'policy_hash': self.flagship.digest, 'engine_hash': flagship_engine_hash(),
            'warnings': result.warnings + ('SHADOW_ONLY_UNCALIBRATED_PORTFOLIO_OBJECTIVE',)})

    def _signal(self, session: date, holdings: Mapping[str, Decimal], cash: Decimal, policy: QuantPolicy,
                costs: CostPolicy, risk: RiskPolicy, label: str, elapsed: int,
                challenger: ChallengerPolicy | None = None) -> tuple[dict[str, Decimal], str, str, dict[str, Decimal]]:
        # Populate the exact V2.2 feature, score-change and attribution caches.
        original = super()._signal(session, holdings, cash, policy, costs, risk, label, elapsed, challenger)
        if self.flagship.construction in {'V22_BASELINE', 'INVERSE_VOLATILITY'}:
            return original
        cutoff = session_close(session)
        features = {s: f for s, f in self._feature_cache[session].items() if isinstance(f, FeatureSnapshot)}
        state = detect_regime(features['SPY'], policy)
        nav = cash + sum((q * self.rows[s][session].close for s, q in holdings.items()), Decimal(0))
        current = {s: q * self.rows[s][session].close / nav for s, q in holdings.items()}
        metadata = [m for m in self.dataset.security_metadata if m.known_at <= cutoff]
        result = construct_flagship(list(self._prior_challenger.values()), features, cutoff, risk,
            self.flagship, state, current=current,
            correlations=pit_correlations({s: self.histories[s] for s in self._prior_challenger}, cutoff, policy.correlation_lookback),
            sector_map={m.symbol: m.sector for m in metadata}, asset_types={m.symbol: m.asset_type for m in metadata},
            extended=self._challenger_cache[session], costs=costs, nav=nav, diagnostic=self.diagnostic)
        account = AccountSnapshot(snapshot_id='v23-replay-risk', account_alias='SIMULATION',
            provider='ISOLATED_QUANT_SIMULATOR', as_of=cutoff,
            total_equity=nav.quantize(Decimal('.0001')), cash=cash.quantize(Decimal('.0001')),
            sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.VERIFIED)
        approved = RiskEngine().approve(result.allocation.feasible_target, account, 'NORMAL', risk,
            metadata={m.symbol: SecurityMetadata(m.symbol, AssetType(m.asset_type), m.sector, None) for m in metadata})
        if any('missing' in v for v in approved.violations):
            raise ValueError('BACKTEST_PIT_SECURITY_METADATA_REQUIRED')
        decision = challenger_rebalance(result.allocation.model_copy(update={'feasible_target': approved.approved}),
            current, nav=nav, risk=risk, policy=self.flagship.baseline, costs=costs,
            sessions_since_rebalance=elapsed, dollar_volumes={s: f.value('dollar_volume_20') for s, f in features.items()})
        return (dict(current) if decision.action == 'BLOCKED' else weights(decision.target), decision.action,
            original[2], original[3])
