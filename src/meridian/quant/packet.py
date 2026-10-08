"""Versioned Chinese research packet; candidate changes have zero trade authority."""

import hashlib
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Literal

from meridian.config import Policies
from meridian.daily_closure import DailyClosureService
from meridian.historical import HistoricalBarSeries
from meridian.orders import OrderPlanner, ProjectedPortfolioValidator
from meridian.quant.backtest import QuantSecurityMetadata, pit_correlations
from meridian.quant.features import ChallengerFeatureSnapshot, compute_challenger_features
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import ChallengerPolicy, CostPolicy
from meridian.quant.portfolio import (
    ChallengerAllocation,
    RebalanceDecision,
    allocate_challenger,
    challenger_rebalance,
    weights,
)
from meridian.quant.regime import RegimeState, detect_regime
from meridian.quant.signals import ChallengerScore, score_challenger
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.reconciliation import ReconciliationEngine
from meridian.risk import RiskEngine
from meridian.schemas import AccountSnapshot, MarketSnapshot, OrderDraft, Side, StableModel
from meridian.security import AssetType, SecurityMetadata

D = Decimal


class SymbolResearchV22(StableModel):
    symbol: str
    analysis_cutoff: datetime
    feature: ChallengerFeatureSnapshot
    score: ChallengerScore | None
    current_exposure: Decimal | None
    preferred_exposure: Decimal
    feasible_exposure: Decimal
    cost_adjusted_exposure: Decimal | None
    eligible_change: Decimal | None
    candidate_action: Literal["BUY_CANDIDATE", "SELL_CANDIDATE", "HOLD", "WAIT"]
    liquidity_status: str
    reasons_for_waiting: tuple[str, ...]
    chinese_explanation: str


class QuantResearchPacketV22(StableModel):
    schema_version: Literal["quant-research-packet.v2.2"] = "quant-research-packet.v2.2"
    analysis_cutoff: datetime
    symbols: tuple[SymbolResearchV22, ...]
    regime: RegimeState
    allocation: ChallengerAllocation
    rebalance: RebalanceDecision | None
    eligible_hypothetical_drafts: tuple[OrderDraft, ...]
    constraint_modifications: tuple[str, ...]
    important_unknowns: tuple[str, ...]
    cost_assumptions: CostPolicy
    data_certification_class: str
    strategy_hash: str
    model_hash: Literal["UNCALIBRATED_NO_PREDICTIVE_MODEL"] = "UNCALIBRATED_NO_PREDICTIVE_MODEL"
    engine_hash: str
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    trade_authorized: Literal[False] = False
    automatic_promotion: Literal[False] = False
    broker_submission: Literal["DISABLED"] = "DISABLED"


@deterministic_decimal
def build_research_packet(histories: Mapping[str, HistoricalBarSeries], symbols: tuple[str, ...], *,
                          cutoff: datetime, policies: Policies, policy: ChallengerPolicy,
                          metadata: tuple[QuantSecurityMetadata, ...] = (), account: AccountSnapshot | None = None,
                          quotes: Mapping[str, MarketSnapshot] | None = None, costs: CostPolicy | None = None,
                          prior: Mapping[str, ChallengerScore] | None = None, diagnostic: bool = False) -> QuantResearchPacketV22:
    if len(set(symbols)) != len(symbols) or any(s != h.canonical_symbol for s, h in histories.items()):
        raise ValueError("CHALLENGER_PACKET_SYMBOL_IDENTITY_MISMATCH")
    if len({m.symbol for m in metadata}) != len(metadata) or any(m.known_at > cutoff for m in metadata):
        raise ValueError("CHALLENGER_PACKET_METADATA_DUPLICATE_OR_FUTURE")
    if "SPY" not in histories or any(s not in histories for s in symbols):
        raise ValueError("CHALLENGER_PACKET_HISTORY_REQUIRED")
    if account is not None and account.account_alias != "Schwab-Paper":
        raise ValueError("CHALLENGER_PACKET_SCHWAB_PAPER_ONLY")
    held_symbols = {h.ticker for h in account.holdings} if account is not None else set()
    if held_symbols - histories.keys():
        raise ValueError("HELD_SYMBOL_HISTORY_REQUIRED_FOR_PACKET")
    costs = costs or CostPolicy()
    feature_rows = {s: compute_challenger_features(histories[s], cutoff, benchmark=histories["SPY"], diagnostic=diagnostic)
                    for s in sorted(set(symbols) | held_symbols | {"SPY"})}
    base = {s: f.base for s, f in feature_rows.items()}
    state = detect_regime(base["SPY"], policy.controls)
    scores = score_challenger([feature_rows[s] for s in sorted(symbols)], policy, state, prior=prior)
    qualified = {s: h for s, h in histories.items() if s in base and base[s].quality_status != "REJECTED"}
    correlations = pit_correlations(qualified, cutoff, policy.controls.correlation_lookback)
    sector_map = {m.symbol: m.sector for m in metadata}
    allocation = allocate_challenger(scores, base, cutoff, policies.risk, policy, state,
                                    correlations=correlations, sector_map=sector_map, diagnostic=diagnostic)
    current = {h.ticker: h.market_value / account.total_equity for h in account.holdings} if account is not None else {}
    nav = account.total_equity if account is not None else None
    rebalance = challenger_rebalance(allocation, current, nav=nav, risk=policies.risk, policy=policy, costs=costs,
        dollar_volumes={s: f.value("dollar_volume_20") for s, f in base.items()}) if nav is not None else None
    blockers = []
    drafts: tuple[OrderDraft, ...] = ()
    security = {m.symbol: SecurityMetadata(m.symbol, AssetType(m.asset_type), m.sector, None) for m in metadata}
    if account is None:
        blockers.append("FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE")
    else:
        blockers.extend(DailyClosureService(policies)._gates(account, dict(quotes or {}), cutoff))
        if any(f.base.synthetic or f.base.quality_status != "VERIFIED" for f in feature_rows.values()):
            blockers.append("CERTIFIED_NON_SYNTHETIC_FEATURES_REQUIRED_FOR_DRAFTS")
        if rebalance is None or nav is None:
            raise ValueError("CHALLENGER_ACCOUNT_NAV_REQUIRED")
        required = set(current) | set(weights(rebalance.target))
        if required - security.keys():
            blockers.append("HELD_AND_TARGET_SECURITY_METADATA_REQUIRED")
        if rebalance.action == "BLOCKED":
            blockers.extend(rebalance.reasons)
        if not blockers:
            approved = RiskEngine().approve(rebalance.target, account, "NORMAL", policies.risk, metadata=security)
            blockers.extend(approved.violations)
            if not blockers:
                reconciliation = ReconciliationEngine().reconcile(account, approved.approved)
                drafts = OrderPlanner().plan(account, reconciliation, dict(quotes or {}), policies.execution, policies.risk, nav)
                projected = ProjectedPortfolioValidator().validate(account, drafts, nav, policies.risk.min_cash_weight,
                    policies.risk.max_position_weight, policies.risk.max_number_positions,
                    sector_map={s: m.sector for s, m in security.items() if m.sector}, max_sector_weight=policies.risk.max_sector_weight)
                blockers.extend(projected.violations)
                buys = tuple(d for d in drafts if d.side is Side.BUY)
                if buys:
                    # Sell recommendations are not fills. Every subset of buys
                    # without sells is bounded by the all-buys/no-sells scenario.
                    partial = ProjectedPortfolioValidator().validate(account, buys, nav, policies.risk.min_cash_weight,
                        policies.risk.max_position_weight, policies.risk.max_number_positions,
                        sector_map={s: m.sector for s, m in security.items() if m.sector}, max_sector_weight=policies.risk.max_sector_weight)
                    blockers.extend("NO_SELL_FILL_SCENARIO:" + r for r in partial.violations)
                    post_buy = dict(current)
                    for draft in buys:
                        post_buy[draft.ticker] = post_buy.get(draft.ticker, D(0)) + draft.estimated_notional / nav
                    vol_bound = sum((v * max(base[s].value("volatility_60") or D(0), policy.controls.volatility_floor)
                                     for s, v in sorted(post_buy.items())), D(0))
                    if sum(post_buy.values(), D(0)) > min(1 - policies.risk.min_cash_weight, state.exposure_ceiling) or vol_bound > policy.controls.target_volatility:
                        blockers.append("NO_SELL_FILL_SCENARIO:CHALLENGER_EXPOSURE_OR_VOLATILITY_BUDGET")
                if blockers:
                    drafts = ()
    unknowns = ["EXPECTED_RETURN_UNCALIBRATED", "ETF_LOOKTHROUGH_OVERLAP_UNKNOWN", "BROAD_MARKET_PARTICIPATION_UNKNOWN",
                "FUNDAMENTALS_DISABLED", "REAL_FINANCIAL_VALIDATION_PENDING", "CERTIFICATION_IS_CALLER_ATTESTATION_NOT_AUTHENTICATION"]
    if costs.spread_bps is None:
        unknowns.append("SPREAD_UNKNOWN")
    preferred, feasible = weights(allocation.preferred_target), weights(allocation.feasible_target)
    adjusted = weights(rebalance.target) if rebalance else {}
    score_map = {s.bridge.symbol: s for s in scores}
    rows = []
    for symbol in sorted(set(symbols) | set(current)):
        if symbol not in feature_rows:
            if symbol not in histories:
                raise ValueError("HELD_SYMBOL_HISTORY_REQUIRED_FOR_PACKET")
            feature_rows[symbol] = compute_challenger_features(histories[symbol], cutoff, benchmark=histories["SPY"], diagnostic=diagnostic)
        eligible = [d for d in drafts if d.ticker == symbol]
        change = sum((d.estimated_notional / nav * (1 if d.side.value == "BUY" else -1) for d in eligible), D(0)) if nav is not None else None
        action = "BUY_CANDIDATE" if change is not None and change > 0 else "SELL_CANDIDATE" if change is not None and change < 0 else "WAIT" if blockers or (rebalance and rebalance.reasons) else "HOLD"
        reasons = tuple(dict.fromkeys([*blockers, *(rebalance.reasons if rebalance else ()), *(score_map[symbol].bridge.exclusion_reasons if symbol in score_map else ())]))
        volume = feature_rows[symbol].base.value("dollar_volume_20")
        rows.append(SymbolResearchV22(symbol=symbol, analysis_cutoff=cutoff, feature=feature_rows[symbol], score=score_map.get(symbol),
            current_exposure=current.get(symbol, D(0)) if account is not None else None, preferred_exposure=preferred.get(symbol, D(0)),
            feasible_exposure=feasible.get(symbol, D(0)), cost_adjusted_exposure=adjusted.get(symbol, D(0)) if rebalance else None,
            eligible_change=change, candidate_action=action, liquidity_status="UNKNOWN" if volume is None else "BELOW_POLICY" if volume < policy.controls.minimum_dollar_volume else "QUALIFIED",
            reasons_for_waiting=reasons, chinese_explanation=("仅供研究；候选变动未获交易授权。"
                + ("等待：" + "、".join(reasons) if reasons else "信号与风险约束已计算，仍需独立人工审核。"))))
    return QuantResearchPacketV22(analysis_cutoff=cutoff, symbols=tuple(rows), regime=state, allocation=allocation,
        rebalance=rebalance, eligible_hypothetical_drafts=drafts, constraint_modifications=tuple([*allocation.modifications, *blockers]),
        important_unknowns=tuple(unknowns), cost_assumptions=costs,
        data_certification_class="SYNTHETIC_DIAGNOSTIC" if any(f.base.synthetic for f in feature_rows.values()) else "UNVERIFIED" if any(f.base.quality_status != "VERIFIED" for f in feature_rows.values()) else "CERTIFIED_RESEARCH_PIT_ADJUSTED",
        strategy_hash=hashlib.sha256(policy.stable_json().encode()).hexdigest(), engine_hash=ENGINE_SOURCE_HASH)
