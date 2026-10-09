"""One-cutoff Quant evidence bridge; public diagnostics never certify history."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime

from meridian.config import Policies
from meridian.historical import HistoricalAdjustmentStatus, HistoricalBarSeries
from meridian.quant.backtest import QuantSecurityMetadata
from meridian.quant.flagship_packet import FlagshipResearchPacket, build_flagship_packet
from meridian.quant.integration import QuantShadowRecord, SymbolComparison, immutable_record
from meridian.quant.packet import QuantResearchPacketV22, build_research_packet
from meridian.quant.policy import ChallengerPolicy
from meridian.quotes import QuoteObservation
from meridian.schemas import AccountSnapshot, StableModel
from meridian.trading_calendar import latest_completed_session, session_close

D = Decimal


class LiveQuantSnapshot(StableModel):
    engine: Literal['V2.2_SHADOW', 'V2.3_SHADOW'] = 'V2.2_SHADOW'
    flagship: FlagshipResearchPacket | None = None
    portfolio_basis: Literal['NO_ACCOUNT_NORMALIZED_RESEARCH', 'ACCOUNT_BOUND_RESEARCH'] = 'NO_ACCOUNT_NORMALIZED_RESEARCH'
    schema_version: Literal['quant-live-information.v1'] = 'quant-live-information.v1'
    analysis_cutoff: AwareDatetime
    quote_hashes: dict[str, str]
    historical_input_hashes: dict[str, str]
    strict_status: Literal['VERIFIED_RESEARCH_AVAILABLE', 'INSUFFICIENT_VERIFIED_HISTORY']
    quant_packet: QuantResearchPacketV22 | None
    shadow_comparison: QuantShadowRecord | None
    provisional_diagnostics: dict[str, Any]
    price_conditions: dict[str, Any]
    missing_reasons: tuple[str, ...]
    expected_turnover: Decimal | None = None
    estimated_cost: Decimal | None = None
    authority: Literal['SHADOW_ONLY'] = 'SHADOW_ONLY'
    financial_oos_evidence_eligible: Literal[False] = False
    trade_authorized: Literal[False] = False
    broker_submission: Literal['DISABLED'] = 'DISABLED'

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


def provisional_diagnostics(series: HistoricalBarSeries, cutoff: datetime) -> dict[str, Any]:
    """Raw bars support within-session observations, never unresolved cross-session returns."""
    eligible = [b for b in series.bars if b.available_at <= cutoff and b.observed_at <= cutoff
                and session_close(b.session, b.calendar) <= cutoff]
    base: dict[str, Any] = {'lane': 'PROVISIONAL_LIVE_RESEARCH', 'provider': series.provider,
        'input_hash': series.stable_hash, 'availability_semantics': 'CURRENT_RETRIEVAL_NOT_HISTORICAL_PIT',
        'historical_known_at': None, 'execution_quote_certified': False,
        'financial_oos_evidence_eligible': False, 'quant_score': None, 'quant_rank': None,
        'momentum': None, 'relative_strength': None, 'volatility': None, 'drawdown': None,
        'corporate_action_coverage': 'UNKNOWN', 'reasons': ['UNRESOLVED_CORPORATE_ACTIONS_NO_CROSS_SESSION_RETURNS']}
    if not eligible:
        return {**base, 'status': 'BLOCKED', 'reasons': ['NO_AVAILABLE_COMPLETED_BARS']}
    if any(b.retrieved_at > cutoff for b in eligible):
        return {**base, 'status': 'BLOCKED', 'reasons': ['PUBLIC_RETRIEVAL_AFTER_CUTOFF']}
    if [b.session for b in eligible] != sorted({b.session for b in eligible}):
        return {**base, 'status': 'BLOCKED', 'reasons': ['DUPLICATE_OR_OUT_OF_SEQUENCE_BARS']}
    last = eligible[-1]
    if last.session != latest_completed_session(cutoff):
        return {**base, 'status': 'BLOCKED', 'reasons': ['STALE_COMPLETED_HISTORY']}
    if any(b.canonical_symbol != series.canonical_symbol or b.canonical_asset_id != series.canonical_asset_id
           or b.currency != 'USD' or min(b.open, b.high, b.low, b.close) <= 0
           or b.low > min(b.open, b.close) or b.high < max(b.open, b.close)
           or b.available_at < b.observed_at for b in eligible):
        return {**base, 'status': 'BLOCKED', 'reasons': ['HISTORY_IDENTITY_PRICE_OR_TIME_INVALID']}
    if len({b.adjustment_status for b in eligible}) != 1:
        return {**base, 'status': 'BLOCKED', 'reasons': ['MIXED_ADJUSTMENT_BASIS']}
    if last.adjustment_status != HistoricalAdjustmentStatus.RAW:
        return {**base, 'status': 'BLOCKED', 'adjustment_basis': last.adjustment_status.value,
                'reasons': ['ADJUSTMENT_AND_ACTION_EVIDENCE_REQUIRED']}
    return {**base, 'status': 'PARTIAL_DIAGNOSTICS', 'adjustment_basis': 'RAW',
        'market_as_of': session_close(last.session, last.calendar).isoformat(),
        'available_at': last.available_at.isoformat(), 'retrieved_at': last.retrieved_at.isoformat(),
        'source': last.source, 'completed_session_close': str(last.close),
        'completed_session_open_to_close': str(last.close / last.open - 1),
        'completed_session_range_fraction': str((last.high - last.low) / last.close),
        'completed_session_dollar_volume': str(last.close * last.volume) if last.volume > 0 else None,
        'liquidity_status': 'PUBLIC_OBSERVED_SESSION_ONLY' if last.volume > 0 else 'UNKNOWN',
        'limitations': ['PUBLIC_UNVERIFIED', 'NO_MOMENTUM_RANK_OR_ALLOCATION', 'NOT_A_V22_SIGNAL']}


def build_live_quant_snapshot(*, histories: Mapping[str, HistoricalBarSeries],
        quotes: Mapping[str, QuoteObservation], cutoff: datetime, policies: Policies,
        policy: ChallengerPolicy, run_id: str, metadata: tuple[QuantSecurityMetadata, ...] = (),
        baseline_weights: Mapping[str, Decimal] | None = None, account: AccountSnapshot | None = None,
        diagnostic: bool = False, engine: Literal['V2.2_SHADOW', 'V2.3_SHADOW'] = 'V2.2_SHADOW') -> LiveQuantSnapshot:
    from meridian.live_advisory import MarketDataFreshnessGate

    if cutoff.tzinfo is None:
        raise ValueError('LIVE_QUANT_CUTOFF_TIMEZONE_REQUIRED')
    if any(s != h.canonical_symbol for s, h in histories.items()):
        raise ValueError('LIVE_HISTORY_SYMBOL_MISMATCH')
    symbols = tuple(sorted(set(policies.universe.tickers)))
    valid_quotes, missing = {}, []
    for symbol, quote in sorted(quotes.items()):
        if (symbol != quote.canonical_symbol or quote.available_at > cutoff
                or MarketDataFreshnessGate().evaluate(quote, cutoff)[0] not in {'LIVE', 'DELAYED'}):
            missing.append(symbol + ':QUOTE_STALE_FUTURE_OR_IDENTITY_INVALID')
        else:
            valid_quotes[symbol] = quote
    packet = None
    if set(symbols) | {'SPY'} <= histories.keys():
        try:
            packet = build_research_packet(histories, symbols, cutoff=cutoff, policies=policies,
                policy=policy, metadata=metadata, diagnostic=diagnostic)
        except ValueError:
            missing.append('QUANT_HISTORY_OR_METADATA_CONTRACT_REJECTED')
    else:
        missing.extend(s + ':HISTORY_UNAVAILABLE' for s in sorted((set(symbols) | {'SPY'}) - histories.keys()))
    qualified = packet is not None and packet.data_certification_class == 'CERTIFIED_RESEARCH_PIT_ADJUSTED'
    if qualified and account is not None:
        # Actual paper observations may inform costs/exposures; absent execution quotes block drafts.
        packet = build_research_packet(histories, symbols, cutoff=cutoff, policies=policies,
            policy=policy, metadata=metadata, account=account, diagnostic=diagnostic)
    if not qualified:
        missing.append('INSUFFICIENT_VERIFIED_HISTORY')
    flagship = None
    if engine == 'V2.3_SHADOW' and (qualified or diagnostic and packet and packet.data_certification_class == 'SYNTHETIC_DIAGNOSTIC'):
        from meridian.quant.policy import CostPolicy
        from meridian.research_terminal import flagship_policy
        try:
            flagship = build_flagship_packet(histories, cutoff, symbols=tuple(s for s in symbols if s != 'SPY'), current={}, nav=D(100000),
                risk=policies.risk, policy=flagship_policy(), costs=CostPolicy(),
                sector_map={m.symbol: m.sector for m in metadata}, asset_types={m.symbol: m.asset_type for m in metadata},
                diagnostic=diagnostic)
        except ValueError:
            missing.append('V23_HISTORY_OR_PORTFOLIO_CONTRACT_REJECTED')
    if engine == 'V2.3_SHADOW' and flagship is None:
        qualified = False
    quote_hashes = {s: hashlib.sha256(q.stable_json().encode()).hexdigest() for s, q in valid_quotes.items()}
    history_hashes = {s: h.stable_hash for s, h in sorted(histories.items())}
    shadow = None
    if packet:
        from meridian.quant.portfolio import weights
        proposed = weights(flagship.allocation.allocation.preferred_target) if flagship else {}
        feasible = weights(flagship.allocation.allocation.feasible_target) if flagship else {}
        scored = {r.symbol: r for r in packet.symbols}
        comparisons = []
        for symbol in symbols:
            row = scored[symbol]
            quote = valid_quotes.get(symbol)
            old_score = max(D(0), quote.last / quote.previous_close - 1) if quote and quote.last and quote.previous_close else None
            new = row.score.bridge.quant_score if qualified and row.score and (engine != 'V2.3_SHADOW' or symbol != 'SPY') else None
            new_weight = feasible.get(symbol, D(0)) if engine == 'V2.3_SHADOW' else row.feasible_exposure
            preferred_weight = proposed.get(symbol, D(0)) if engine == 'V2.3_SHADOW' else row.preferred_exposure
            old_weight = (baseline_weights or {}).get(symbol, D(0))
            comparisons.append(SymbolComparison(symbol=symbol, old_quant_score=old_score, new_quant_score=new,
                old_target_weight=old_weight, new_target_weight=new_weight,
                proposed_target_weight=preferred_weight, weight_difference=new_weight - old_weight,
                reasons=row.reasons_for_waiting + (() if qualified else ('INSUFFICIENT_VERIFIED_HISTORY',))))
        shadow = QuantShadowRecord(run_id=run_id, as_of=cutoff,
            market_snapshot_hash=hashlib.sha256('|'.join(f'{s}:{h}' for s, h in quote_hashes.items()).encode()).hexdigest(),
            policy_hash=flagship.allocation.policy_hash if flagship else packet.strategy_hash,
            engine_hash=flagship.engine_hash if flagship else packet.engine_hash,
            history_hashes=tuple(history_hashes.values()),
            status='SHADOW_COMPUTED' if qualified else 'INSUFFICIENT_DATA', symbols=tuple(comparisons),
            scores=tuple(s.bridge for s in flagship.scores) if flagship else tuple(r.score.bridge for r in packet.symbols if r.score), regime=packet.regime,
            expected_turnover=flagship.cost_adjusted_proposal.expected_turnover if flagship else packet.rebalance.expected_turnover if packet.rebalance else D(0),
            estimated_cost_fraction=flagship.cost_adjusted_proposal.estimated_cost / D(100000) if flagship else packet.rebalance.estimated_cost / account.total_equity if packet.rebalance and account and account.total_equity else D(0),
            reasons=(('V23_NORMALIZED_REFERENCE_COST_NOT_ACCOUNT_COST' if flagship else 'ACCOUNT_BOUND_RESEARCH_COST_ESTIMATE' if packet.rebalance else 'NO_ACCOUNT_BOUND_TURNOVER_ESTIMATE'), 'LEGACY_TARGET_IS_NOT_CANONICAL_RUN',
                     engine + '_RESEARCH_ONLY_NOT_CALIBRATED_FORECAST'))
    provisional = {s: provisional_diagnostics(h, cutoff) for s, h in sorted(histories.items())}
    conditions = {}
    for symbol in symbols:
        quote = valid_quotes.get(symbol)
        row = next((r for r in packet.symbols if r.symbol == symbol), None) if packet else None
        atr = row.feature.base.value('atr14') if qualified and row else None
        sma = row.feature.base.value('sma20') if qualified and row else None
        price = quote.last if quote and quote.last and quote.last > 0 else None
        zone = None
        if price and atr and sma:
            anchor = sma
            half_width = atr / 2
            zone = (max(D('.01'), anchor - half_width), anchor + half_width)
        conditions[symbol] = {'observed_price': str(price) if price else None,
            'quote_hash': quote_hashes.get(symbol), 'observation_at': quote.observed_at.isoformat() if quote else None,
            'timezone': 'America/New_York', 'quantitative_entry_zone': tuple(str(v) for v in zone) if zone else None,
            'method': 'SMA20_PULLBACK_WITH_HALF_ATR14' if zone else None,
            'price_basis': 'ADJUSTED_HISTORY_RESEARCH_UNITS_NOT_EXECUTION_UNITS',
            'feature_input_hash': row.feature.base.input_hash if qualified and row else None,
            'feature_session': row.feature.base.last_session.isoformat() if qualified and row and row.feature.base.last_session else None,
            'assumptions': ['HISTORY_AND_CURRENT_PRICE_BASIS_COMPATIBLE', 'NO_NEW_OVERNIGHT_CORPORATE_ACTION'] if zone else [],
            'fair_value': None, 'user_approved_executable_limit': None,
            'assessment': 'WAIT_FOR_PRICE' if zone and price and price > zone[1] else 'CONDITIONAL_RESEARCH_ONLY' if zone else 'WAIT_FOR_EVIDENCE',
            'invalidation_condition': 'Recompute after a new completed session, corporate action or stale observation.',
            'reason': 'No valuation or calibrated expected return; manual review required.' if zone else 'Qualified ATR/price basis/current observation unavailable; no invented entry price.'}
    return LiveQuantSnapshot(engine=engine, flagship=flagship, analysis_cutoff=cutoff, quote_hashes=quote_hashes,
        historical_input_hashes=history_hashes, strict_status='VERIFIED_RESEARCH_AVAILABLE' if qualified else 'INSUFFICIENT_VERIFIED_HISTORY',
        quant_packet=packet, shadow_comparison=shadow, provisional_diagnostics=provisional,
        price_conditions=conditions, missing_reasons=tuple(missing),
        expected_turnover=flagship.cost_adjusted_proposal.expected_turnover if flagship else packet.rebalance.expected_turnover if packet and packet.rebalance else None,
        estimated_cost=None if engine == 'V2.3_SHADOW' else packet.rebalance.estimated_cost if packet and packet.rebalance else None)


def live_recommendations(snapshot: LiveQuantSnapshot, request=None) -> tuple:
    """Reuse the terminal decision contract on the exact sealed live snapshot."""
    from meridian.research_recommendations import build_recommendations
    from meridian.research_terminal import (
        QuantTerminalRow,
        QuantTerminalSnapshot,
        risk_policy_fingerprint,
    )
    packet = snapshot.quant_packet
    qualified = snapshot.strict_status == 'VERIFIED_RESEARCH_AVAILABLE'
    scores = {s.bridge.symbol: s for s in snapshot.flagship.scores} if snapshot.flagship else {}
    rows = []
    for symbol in sorted(snapshot.price_conditions):
        raw = next((r for r in packet.symbols if r.symbol == symbol), None) if packet else None
        score = scores.get(symbol) or (raw.score if raw else None)
        eligible = bool(qualified and score and not score.bridge.exclusion_reasons and (snapshot.engine != 'V2.3_SHADOW' or symbol != 'SPY'))
        rows.append(QuantTerminalRow(symbol=symbol, evidence_id='quant-' + snapshot.digest + '-' + symbol,
            score=score.bridge.quant_score if eligible and score else None,
            rank=score.bridge.relative_rank if eligible and score else None,
            quality=raw.feature.base.quality_status if raw else 'MISSING', eligible=eligible,
            reasons=('BENCHMARK_REFERENCE_NOT_V23_CANDIDATE',) if snapshot.engine == 'V2.3_SHADOW' and symbol == 'SPY' else tuple(score.bridge.exclusion_reasons) if qualified and score else snapshot.missing_reasons,
            chinese_explanation='影子研究；不能直接下单。'))
    terminal = QuantTerminalSnapshot(engine=snapshot.engine, flagship=snapshot.flagship,
        public_diagnostics=snapshot.provisional_diagnostics,
        status='AVAILABLE' if qualified else 'BLOCKED', analysis_cutoff=snapshot.analysis_cutoff,
        request_hash=snapshot.digest, input_hashes=snapshot.historical_input_hashes,
        policy_hash=snapshot.flagship.allocation.policy_hash if snapshot.flagship else packet.strategy_hash if packet else '0' * 64,
        risk_policy_hash=risk_policy_fingerprint(),
        engine_hash=snapshot.flagship.engine_hash if snapshot.flagship else packet.engine_hash if packet else '0' * 64,
        packet=packet, rows=tuple(rows), reasons=snapshot.missing_reasons,
        certification=packet.data_certification_class if packet else 'UNKNOWN')
    return build_recommendations(terminal, request=request)


def persist_live_quant(snapshot: LiveQuantSnapshot, directory: Path) -> Path:
    return immutable_record(directory / (snapshot.digest + '.json'), snapshot.stable_json())
