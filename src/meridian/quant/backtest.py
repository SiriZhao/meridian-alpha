"""Isolated event-driven walk-forward replay, never an execution adapter.

Close features are known only after close. Pending targets execute at the next
session open using an explicit friction assumption, whole shares and cash caps.
No daily close-to-same-close execution, data filling or canonical ledger access.
"""

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Literal

from pydantic import Field, model_validator

from meridian.config import RiskPolicy
from meridian.historical import HistoricalBarCertification, HistoricalBarSeries
from meridian.lab_evaluation import rank_correlation
from meridian.quant.features import (
    ChallengerFeatureSnapshot,
    compute_challenger_features,
    compute_features,
    eligible_bars,
    mean,
)
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import ChallengerPolicy, CostPolicy, QuantPolicy
from meridian.quant.portfolio import (
    allocate,
    allocate_challenger,
    challenger_rebalance,
    cost_aware_target,
    target_from_weights,
    weights,
)
from meridian.quant.regime import detect_regime
from meridian.quant.signals import ChallengerScore, QuantFactorEngine, score_challenger
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.schemas import StableModel
from meridian.trading_calendar import is_trading_session, session_close, session_open

D = Decimal
INITIAL_NAV = D("100000")


class UniverseMembership(StableModel):
    symbol: str
    start: date
    end: date | None = None
    known_at: datetime
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self) -> "UniverseMembership":
        if self.end is not None and self.end < self.start:
            raise ValueError("UNIVERSE_INVALID_INTERVAL")
        return self


class QuantDataset(StableModel):
    version: str = "quant-dataset-v1"
    series: tuple[HistoricalBarSeries, ...]
    memberships: tuple[UniverseMembership, ...]
    evidence_status: Literal["VERIFIED_PIT", "UNVERIFIED", "SYNTHETIC_DIAGNOSTIC"] = "UNVERIFIED"
    corporate_actions_covered_until: date | None = None
    corporate_action_source: str | None = None
    universe_basis: Literal["PIT_MEMBERSHIP", "PREDECLARED_STATIC", "CURRENT_SURVIVORS"] = "CURRENT_SURVIVORS"
    description: str
    security_metadata: tuple["QuantSecurityMetadata", ...] = ()

    @model_validator(mode="after")
    def identities(self) -> "QuantDataset":
        names = [s.canonical_symbol for s in self.series]
        if len(set(names)) != len(names) or "SPY" not in names:
            raise ValueError("DATASET_DUPLICATE_OR_MISSING_SPY")
        if any(m.symbol not in names for m in self.memberships):
            raise ValueError("DATASET_MEMBERSHIP_WITHOUT_SERIES")
        if len({m.symbol for m in self.memberships}) != len(self.memberships):
            raise ValueError("DATASET_MEMBERSHIP_DUPLICATE")
        if len({m.symbol for m in self.security_metadata}) != len(self.security_metadata):
            raise ValueError("DATASET_METADATA_DUPLICATE")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class QuantSecurityMetadata(StableModel):
    symbol: str
    asset_type: Literal["EQUITY", "DIVERSIFIED_ETF"]
    sector: str | None = None
    known_at: datetime
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def equity_sector(self) -> "QuantSecurityMetadata":
        if self.asset_type == "EQUITY" and not self.sector:
            raise ValueError("PIT_EQUITY_SECTOR_REQUIRED")
        return self


class WalkForwardFold(StableModel):
    name: str
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date
    embargo_sessions: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def chronological(self) -> "WalkForwardFold":
        if not (self.train_start <= self.train_end < self.validation_start <= self.validation_end < self.test_start <= self.test_end):
            raise ValueError("WALK_FORWARD_CHRONOLOGY_INVALID")
        return self


class SimulatedTrade(StableModel):
    symbol: str
    signal_at: datetime
    execution_at: datetime
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal
    commission: Decimal
    friction: Decimal

    @model_validator(mode="after")
    def delay(self) -> "SimulatedTrade":
        if self.signal_at >= self.execution_at or self.quantity <= 0:
            raise ValueError("BACKTEST_SAME_SESSION_OR_INVALID_FILL")
        return self


class ReplayDay(StableModel):
    session: date
    nav: Decimal
    cash: Decimal
    exposure: Decimal
    daily_return: Decimal
    benchmark_return: Decimal
    turnover: Decimal
    costs: Decimal
    regime: str
    decision: str
    factor_ic: Decimal | None = None
    risk_drift: tuple[str, ...] = ()


class ReplayResult(StableModel):
    strategy: str
    fold: str
    partition: str
    dataset_hash: str
    policy_hash: str
    cost_hash: str
    risk_hash: str
    engine_hash: str
    evidence_status: str
    days: tuple[ReplayDay, ...]
    trades: tuple[SimulatedTrade, ...]
    warnings: tuple[str, ...]
    initial_nav: Decimal
    automatic_promotion: Literal[False] = False


def rank_ic(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    return rank_correlation(list(left), list(right))


@deterministic_decimal
def pit_correlations(histories: Mapping[str, HistoricalBarSeries], cutoff: datetime,
                     lookback: int) -> dict[tuple[str, str], Decimal]:
    result = {}
    symbols = sorted(histories)
    for i, left in enumerate(symbols):
        a = eligible_bars(histories[left], cutoff)[-lookback - 1:]
        for right in symbols[i + 1:]:
            b = eligible_bars(histories[right], cutoff)[-lookback - 1:]
            if len(a) != lookback + 1 or [v.session for v in a] != [v.session for v in b]:
                continue
            x = [v.close / p.close - 1 for p, v in zip(a, a[1:], strict=False)]
            y = [v.close / p.close - 1 for p, v in zip(b, b[1:], strict=False)]
            mx, my = mean(x), mean(y)
            vx, vy = sum(((v - mx) ** 2 for v in x), D(0)), sum(((v - my) ** 2 for v in y), D(0))
            if vx and vy:
                result[left, right] = max(D(-1), min(D(1), sum(((u - mx) * (v - my) for u, v in zip(x, y, strict=True)), D(0)) / (vx * vy).sqrt()))
    return result


class WalkForwardRunner:
    def __init__(self, dataset: QuantDataset, *, diagnostic: bool = False) -> None:
        self.dataset = dataset
        self.diagnostic = diagnostic
        self.histories = {s.canonical_symbol: s for s in dataset.series}
        self.rows = {s: {b.session: b for b in series.bars} for s, series in self.histories.items()}
        self._feature_cache: dict[date, dict[str, object]] = {}
        self._challenger_cache: dict[date, dict[str, ChallengerFeatureSnapshot]] = {}
        self._prior_challenger: dict[str, ChallengerScore] = {}

    def _preflight(self, start: date, end: date) -> tuple[date, ...]:
        if self.dataset.evidence_status == "UNVERIFIED":
            raise ValueError("BACKTEST_PIT_DATA_UNVERIFIED")
        synthetic = any(b.certification.value == "SYNTHETIC" for s in self.dataset.series for b in s.bars)
        if synthetic and self.dataset.evidence_status != "SYNTHETIC_DIAGNOSTIC":
            raise ValueError("BACKTEST_SYNTHETIC_EVIDENCE_STATUS_MISMATCH")
        if self.dataset.evidence_status == "SYNTHETIC_DIAGNOSTIC" and not self.diagnostic:
            raise ValueError("BACKTEST_SYNTHETIC_REQUIRES_DIAGNOSTIC")
        if self.dataset.universe_basis == "CURRENT_SURVIVORS":
            raise ValueError("BACKTEST_SURVIVORSHIP_BIAS_UNRESOLVED")
        if (self.dataset.corporate_actions_covered_until is None or self.dataset.corporate_actions_covered_until < end
                or not self.dataset.corporate_action_source):
            raise ValueError("BACKTEST_CORPORATE_ACTION_COVERAGE_REQUIRED")
        calendar = sorted(self.rows["SPY"])
        if not calendar or calendar[0] >= start or end > calendar[-1]:
            raise ValueError("BACKTEST_PERIOD_OR_WARMUP_NOT_COVERED")
        selected = tuple(s for s in calendar if start <= s <= end)
        if not selected:
            raise ValueError("BACKTEST_EMPTY_PERIOD")
        # Missing SPY rows must never compress the calendar and turn a multi-
        # session return into an apparently single-session observation.
        expected = []
        cursor = start
        while cursor <= end:
            if is_trading_session(cursor):
                expected.append(cursor)
            cursor += timedelta(days=1)
        if selected != tuple(expected):
            raise ValueError("BACKTEST_MISSING_BENCHMARK_SESSION")
        return selected

    @deterministic_decimal
    def run(self, policy: QuantPolicy, costs: CostPolicy, risk: RiskPolicy, fold: WalkForwardFold,
            *, partition: Literal["validation", "test"] = "test", strategy: str | None = None,
            initial_nav: Decimal = INITIAL_NAV, challenger: ChallengerPolicy | None = None) -> ReplayResult:
        if not initial_nav.is_finite() or initial_nav <= 0:
            raise ValueError("BACKTEST_INITIAL_NAV_INVALID")
        label = strategy or policy.strategy
        if label not in {"CASH", "SPY_BUY_HOLD", "SPY_POLICY", "EQUAL_WEIGHT", "A0", "A1", "A2", "A3", "A4", "V22"}:
            raise ValueError("BACKTEST_STRATEGY_INVALID")
        if (label == "V22") != (challenger is not None) or (challenger is not None and challenger.controls != policy):
            raise ValueError("BACKTEST_CHALLENGER_POLICY_MISMATCH")
        self._prior_challenger = {}
        if label.startswith("A") and label != policy.strategy:
            raise ValueError("BACKTEST_POLICY_STRATEGY_MISMATCH")
        start, end = (fold.test_start, fold.test_end) if partition == "test" else (fold.validation_start, fold.validation_end)
        sessions = self._preflight(start, end)
        # Split separation is validated against the actual trading calendar.
        previous_end = fold.validation_end if partition == "test" else fold.train_end
        preceding = [s for s in sorted(self.rows["SPY"]) if previous_end < s < start]
        if len(preceding) < fold.embargo_sessions:
            raise ValueError("BACKTEST_EMBARGO_NOT_SATISFIED")
        previous = max(s for s in self.rows["SPY"] if s < sessions[0])
        cash = initial_nav
        holdings: dict[str, Decimal] = {}
        prior_nav = initial_nav
        pending: dict[str, Decimal] = {}
        signal_at = session_close(previous)
        days, trades = [], []
        warnings = {"RISK_FREE_RETURN_ASSUMED_ZERO", "SPREAD_UNKNOWN" if costs.spread_bps is None else "SPREAD_POLICY_ASSUMPTION_NOT_OBSERVED",
                    "RESEARCH_SIMULATOR_NOT_MANUAL_LIMIT_FILL_MODEL", "NO_OOS_PARAMETER_FITTING", "GROSS_TRADED_NOTIONAL_OVER_NAV_TURNOVER"}
        if self.dataset.evidence_status == "SYNTHETIC_DIAGNOSTIC":
            warnings.add("SYNTHETIC_RESULTS_HAVE_NO_FINANCIAL_EVIDENCE_AUTHORITY")
        if label == "SPY_BUY_HOLD":
            warnings.add("UNCONSTRAINED_BENCHMARK_NOT_A_POLICY_ELIGIBLE_PORTFOLIO")
        elapsed = 5
        prior_scores: dict[str, Decimal] = {}
        prior_closes: dict[str, Decimal] = {}
        # Build the first close signal before any OOS simulated open fill.
        pending, decision, regime, prior_scores = self._signal(previous, holdings, cash, policy, costs, risk, label, elapsed, challenger)
        prior_closes = {s: row[previous].close for s, row in self.rows.items() if previous in row}
        for index, session in enumerate(sessions):
            opening = session_open(session)
            close_time = session_close(session)
            active = {m.symbol for m in self.dataset.memberships if m.start <= session and (m.end is None or session <= m.end) and m.known_at <= signal_at}
            if label in {"SPY_BUY_HOLD", "SPY_POLICY"}:
                active.add("SPY")
            required = set(holdings) | set(pending) | {"SPY"}
            if any(session not in self.rows[s] for s in required):
                raise ValueError("BACKTEST_MISSING_EXECUTION_OR_MARK_BAR")
            session_bars = {s: rows[session] for s, rows in self.rows.items() if session in rows}
            permitted = {HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED}
            if self.diagnostic:
                permitted.add(HistoricalBarCertification.SYNTHETIC)
            if any(session_bars[s].certification not in permitted or session_bars[s].canonical_symbol != s
                   or session_bars[s].currency != "USD"
                   or min(session_bars[s].open, session_bars[s].high, session_bars[s].low, session_bars[s].close) <= 0
                   for s in required):
                raise ValueError("BACKTEST_EXECUTION_OR_MARK_PRICE_UNVERIFIED")
            if any(b.observed_at < close_time or b.available_at < b.observed_at or b.available_at > close_time
                   or b.quality.value != "VERIFIED" or b.adjustment_status.value != "FULLY_ADJUSTED_OHLCV"
                   for b in session_bars.values()):
                raise ValueError("BACKTEST_PREMATURE_PRICE_AVAILABILITY")
            nav_open = cash + sum((q * session_bars[s].open for s, q in holdings.items()), D(0))
            day_trades = []
            turn_budget = nav_open * min(policy.max_turnover, risk.max_daily_turnover)
            if label == "SPY_BUY_HOLD":
                turn_budget = nav_open * 2
            # Sells precede buys in the simulator: only actually simulated
            # proceeds become spendable. This does not alter manual planning.
            symbols = set(holdings) | set(pending)
            deltas = {s: (pending.get(s, D(0)) * nav_open / session_bars[s].open).quantize(D(1), rounding=ROUND_DOWN) - holdings.get(s, D(0)) for s in symbols}
            if label == "SPY_BUY_HOLD" and holdings:
                deltas = dict.fromkeys(symbols, D(0))
            if decision in {"NO_ACTION", "BLOCKED"}:
                deltas = dict.fromkeys(symbols, D(0))
            ordered = sorted(symbols, key=lambda s: (deltas[s] >= 0, s))
            for symbol in ordered:
                delta = deltas[symbol]
                if delta == 0:
                    continue
                if delta > 0 and symbol not in active:
                    raise ValueError("BACKTEST_FUTURE_OR_EXPIRED_MEMBERSHIP")
                bar = session_bars[symbol]
                reference = bar.open
                price = reference * (1 + costs.adverse_fraction if delta > 0 else 1 - costs.adverse_fraction)
                cap = nav_open * risk.max_single_order_nav_percent if label != "SPY_BUY_HOLD" else nav_open
                qty = min(abs(delta), (min(turn_budget, cap) / reference).quantize(D(1), rounding=ROUND_DOWN))
                if delta > 0:
                    mark_nav = cash + sum((q * session_bars[s].open for s, q in holdings.items()), D(0))
                    minimum_cash = D(0) if label == "SPY_BUY_HOLD" else risk.min_cash_weight
                    cash_capacity = (cash - minimum_cash * mark_nav - costs.commission_per_order * (1 - minimum_cash)) / (price - minimum_cash * (price - reference))
                    qty = min(qty, max(D(0), cash_capacity).quantize(D(1), rounding=ROUND_DOWN))
                    if label != "SPY_BUY_HOLD":
                        current_value = holdings.get(symbol, D(0)) * reference
                        weight_capacity = (risk.max_position_weight * (mark_nav - costs.commission_per_order) - current_value) / (reference + risk.max_position_weight * (price - reference))
                        qty = min(qty, max(D(0), weight_capacity).quantize(D(1), rounding=ROUND_DOWN))
                        known_meta = {m.symbol: m for m in self.dataset.security_metadata if m.known_at <= signal_at}
                        meta = known_meta.get(symbol)
                        if risk.max_sector_weight < 1 and meta is None:
                            raise ValueError("BACKTEST_PIT_SECURITY_METADATA_REQUIRED")
                        if meta is not None and meta.sector:
                            sector_value = sum((q * session_bars[s].open for s, q in holdings.items() if s in known_meta and known_meta[s].sector == meta.sector), D(0))
                            sector_capacity = (risk.max_sector_weight * (mark_nav - costs.commission_per_order) - sector_value) / (reference + risk.max_sector_weight * (price - reference))
                            qty = min(qty, max(D(0), sector_capacity).quantize(D(1), rounding=ROUND_DOWN))
                else:
                    qty = min(qty, holdings.get(symbol, D(0)))
                notional = qty * reference
                if qty <= 0 or notional < policy.minimum_trade_notional:
                    continue
                if not self.diagnostic and bar.certification != HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED:
                    raise ValueError("BACKTEST_EXECUTION_PRICE_UNVERIFIED")
                fee = costs.commission_per_order
                if delta < 0 and qty * price <= fee:
                    continue
                if delta > 0:
                    cash -= qty * price + fee
                    holdings[symbol] = holdings.get(symbol, D(0)) + qty
                else:
                    cash += qty * price - fee
                    holdings[symbol] -= qty
                turn_budget -= notional
                trade = SimulatedTrade(symbol=symbol, signal_at=signal_at, execution_at=opening,
                                       side="BUY" if delta > 0 else "SELL", quantity=qty,
                                       reference_price=reference, fill_price=price, commission=fee,
                                       friction=abs(price - reference) * qty)
                day_trades.append(trade)
            holdings = {s: q for s, q in holdings.items() if q > 0}
            if cash < 0 or any(q < 0 for q in holdings.values()):
                raise ValueError("BACKTEST_NEGATIVE_CASH_OR_SHORT_POSITION")
            nav = cash + sum((q * session_bars[s].close for s, q in holdings.items()), D(0))
            benchmark_return = session_bars["SPY"].close / (session_bars["SPY"].open if index == 0 else self.rows["SPY"][previous].close) - 1
            symbols_ic = sorted(set(prior_scores) & set(prior_closes) & set(session_bars))
            ic = rank_ic([prior_scores[s] for s in symbols_ic], [session_bars[s].close / prior_closes[s] - 1 for s in symbols_ic])
            drift = []
            if label != "SPY_BUY_HOLD":
                if cash / nav < risk.min_cash_weight:
                    drift.append("MARK_TO_MARKET_CASH_FLOOR_DRIFT")
                if any(q * session_bars[s].close / nav > risk.max_position_weight for s, q in holdings.items()):
                    drift.append("MARK_TO_MARKET_POSITION_CAP_DRIFT")
                known_meta = {m.symbol: m for m in self.dataset.security_metadata if m.known_at <= close_time}
                sectors = {m.sector for m in known_meta.values() if m.sector}
                if any(sum((q * session_bars[s].close for s, q in holdings.items() if s in known_meta and known_meta[s].sector == sector), D(0)) / nav > risk.max_sector_weight for sector in sectors):
                    drift.append("MARK_TO_MARKET_SECTOR_CAP_DRIFT")
            days.append(ReplayDay(session=session, nav=nav, cash=cash, exposure=(nav - cash) / nav,
                                  daily_return=nav / prior_nav - 1, benchmark_return=benchmark_return,
                                  turnover=sum((t.quantity * t.reference_price for t in day_trades), D(0)) / nav_open,
                                  costs=sum((t.commission + t.friction for t in day_trades), D(0)),
                                  regime=regime, decision=decision, factor_ic=ic, risk_drift=tuple(drift)))
            trades.extend(day_trades)
            elapsed = 0 if day_trades else elapsed + 1
            prior_nav, previous, signal_at = nav, session, close_time
            if index + 1 < len(sessions):
                pending, decision, regime, prior_scores = self._signal(session, holdings, cash, policy, costs, risk, label, elapsed, challenger)
                prior_closes = {s: row[session].close for s, row in self.rows.items() if session in row}
        def digest(model: StableModel) -> str:
            return hashlib.sha256(model.stable_json().encode()).hexdigest()
        return ReplayResult(strategy=label, fold=fold.name, partition=partition, dataset_hash=self.dataset.digest,
                            policy_hash=digest(challenger or policy), cost_hash=digest(costs), risk_hash=hashlib.sha256(risk.model_dump_json().encode()).hexdigest(), engine_hash=ENGINE_SOURCE_HASH,
                            evidence_status=self.dataset.evidence_status, days=tuple(days), trades=tuple(trades),
                            warnings=tuple(sorted(warnings)), initial_nav=initial_nav)

    def _signal(self, session: date, holdings: Mapping[str, Decimal], cash: Decimal, policy: QuantPolicy,
                costs: CostPolicy, risk: RiskPolicy, label: str, elapsed: int,
                challenger: ChallengerPolicy | None = None) -> tuple[dict[str, Decimal], str, str, dict[str, Decimal]]:
        cutoff = session_close(session)
        eligible = {m.symbol for m in self.dataset.memberships if m.start <= session and (m.end is None or session <= m.end) and m.known_at <= cutoff}
        # Shared immutable feature observations make all experimental variants
        # consume exactly the same input information. No fitted parameters.
        from meridian.quant.features import FeatureSnapshot
        cached = self._feature_cache.get(session)
        if cached is None:
            features = {s: compute_features(self.histories[s], cutoff, benchmark=self.histories["SPY"], diagnostic=self.diagnostic) for s in sorted(eligible | {"SPY"})}
            self._feature_cache[session] = dict(features)
        else:
            features = {s: f for s, f in cached.items() if isinstance(f, FeatureSnapshot)}
        if any(f.quality_status == "REJECTED" for f in features.values()):
            raise ValueError("BACKTEST_FEATURE_QUALITY_REJECTED:" + ";".join(sorted({r for f in features.values() for r in f.reasons})))
        state = detect_regime(features["SPY"], policy)
        regime = state.trend + "/" + state.volatility
        nav = cash + sum((q * self.rows[s][session].close for s, q in holdings.items()), D(0))
        current = {s: q * self.rows[s][session].close / nav for s, q in holdings.items()}
        if label == "CASH":
            return {}, "CASH", regime, {}
        if label == "SPY_BUY_HOLD":
            return {"SPY": D(1)} if not holdings else dict(current), "BUY_HOLD", regime, {}
        challenger_allocation = None
        if label == "V22" and challenger is not None:
            extended = self._challenger_cache.get(session)
            if extended is None:
                extended = {s: compute_challenger_features(self.histories[s], cutoff, benchmark=self.histories["SPY"], diagnostic=self.diagnostic)
                            for s in sorted(eligible)}
                self._challenger_cache[session] = extended
            challenger_scores = score_challenger([extended[s] for s in sorted(eligible)], challenger, state, prior=self._prior_challenger)
            self._prior_challenger = {s.bridge.symbol: s for s in challenger_scores}
            correlations = pit_correlations({s: self.histories[s] for s in eligible}, cutoff, policy.correlation_lookback)
            challenger_allocation = allocate_challenger(challenger_scores, features, cutoff, risk, challenger, state,
                correlations=correlations, sector_map={m.symbol: m.sector for m in self.dataset.security_metadata if m.known_at <= cutoff},
                diagnostic=self.diagnostic)
            target = challenger_allocation.feasible_target
            score_map = {s.bridge.symbol: s.bridge.quant_score for s in challenger_scores}
        elif label in {"EQUAL_WEIGHT", "SPY_POLICY"}:
            symbols = ["SPY"] if label == "SPY_POLICY" else sorted(eligible)[:risk.max_number_positions]
            unit = min(risk.max_position_weight, (1 - risk.min_cash_weight) / len(symbols)) if symbols else D(0)
            target = target_from_weights(dict.fromkeys(symbols, unit), cutoff, "equal-weight-v1")
            score_map = {}
        else:
            scores = QuantFactorEngine().score([features[s] for s in sorted(eligible)], policy, state)
            correlations = pit_correlations({s: self.histories[s] for s in eligible}, cutoff, policy.correlation_lookback) if policy.correlation_limit is not None else None
            target = allocate(scores, features, cutoff, risk, policy, state, correlations=correlations)
            if label == "A0":
                from meridian.allocation import DeterministicFallbackAllocator
                from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState
                simulated_account = AccountSnapshot(snapshot_id="quant-replay", account_alias="SIMULATION",
                                                     provider="ISOLATED_QUANT_SIMULATOR", as_of=cutoff,
                                                     total_equity=nav.quantize(D("0.0001")), cash=cash.quantize(D("0.0001")), sync_state=AccountSyncState.SYNCED,
                                                     freshness_state=FreshnessState.VERIFIED)
                target = DeterministicFallbackAllocator().allocate([s.domain_score() for s in scores], {}, simulated_account, risk)
            score_map = {s.symbol: s.quant_score for s in scores}
        from meridian.risk import RiskEngine
        from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState
        from meridian.security import AssetType, SecurityMetadata
        account = AccountSnapshot(snapshot_id="quant-replay-risk", account_alias="SIMULATION",
                                  provider="ISOLATED_QUANT_SIMULATOR", as_of=cutoff,
                                  total_equity=nav.quantize(D("0.0001")), cash=cash.quantize(D("0.0001")),
                                  sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.VERIFIED)
        metadata = {m.symbol: SecurityMetadata(m.symbol, AssetType(m.asset_type), m.sector, None)
                    for m in self.dataset.security_metadata if m.known_at <= cutoff}
        risk_result = RiskEngine().approve(target, account, "NORMAL", risk, metadata=metadata)
        if any("missing" in v for v in risk_result.violations):
            raise ValueError("BACKTEST_PIT_SECURITY_METADATA_REQUIRED")
        target = risk_result.approved
        if challenger_allocation is not None and challenger is not None:
            decision = challenger_rebalance(challenger_allocation.model_copy(update={"feasible_target": target}), current,
                nav=nav, risk=risk, policy=challenger, costs=costs, sessions_since_rebalance=elapsed,
                dollar_volumes={s: f.value("dollar_volume_20") for s, f in features.items()})
        else:
            decision = cost_aware_target(target, current, nav=nav, risk=risk, policy=policy, costs=costs,
                                     sessions_since_rebalance=elapsed,
                                     dollar_volumes={s: f.value("dollar_volume_20") for s, f in features.items()})
        return (dict(current) if decision.action == "BLOCKED" else weights(decision.target), decision.action, regime, score_map)
