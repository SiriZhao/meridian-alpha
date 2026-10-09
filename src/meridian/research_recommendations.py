"""Evidence-bound research decisions. No model-authored orders or inferred accounts."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.daily_research import DailyResearchInput
from meridian.gpt_native_research import NativeResearchResult
from meridian.quant.features import FeatureSnapshot
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.portfolio import weights
from meridian.research_terminal import QuantTerminalSnapshot
from meridian.schemas import StableModel

D = Decimal
Category = Literal["BUY_CANDIDATE", "ACCUMULATE_CONDITIONALLY", "HOLD", "TRIM_CANDIDATE",
                   "EXIT_REVIEW", "WATCH", "WAIT_FOR_EVIDENCE", "NO_ACTION"]
AdviceState = Literal["RESEARCH_ONLY", "CONDITIONAL_PLAN", "MANUAL_TICKET_READY", "PAPER_ONLY", "BLOCKED"]


class ResearchPricePlan(StableModel):
    version: Literal["research-price-plan.v1"] = "research-price-plan.v1"
    symbol: str
    analysis_cutoff: AwareDatetime
    observed_price: Decimal = Field(gt=0, allow_inf_nan=False)
    observed_at: AwareDatetime
    source: str
    quote_evidence_id: str
    feature_input_hash: str
    feature_session: str
    lower: Decimal = Field(gt=0, allow_inf_nan=False)
    upper: Decimal = Field(gt=0, allow_inf_nan=False)
    method: Literal["SMA20_PULLBACK_WITH_HALF_ATR14"] = "SMA20_PULLBACK_WITH_HALF_ATR14"
    measurement: dict[str, Decimal]
    scenario: Literal["TREND_PULLBACK_RESEARCH_NOT_FAIR_VALUE"] = "TREND_PULLBACK_RESEARCH_NOT_FAIR_VALUE"
    price_basis: Literal["ADJUSTED_HISTORY_RESEARCH_UNITS_NOT_EXECUTION_UNITS"] = "ADJUSTED_HISTORY_RESEARCH_UNITS_NOT_EXECUTION_UNITS"
    assessment: Literal["ABOVE_ZONE", "IN_ZONE", "BELOW_ZONE_REVIEW"]
    recalculate_when: tuple[str, ...] = ("NEW_COMPLETED_SESSION", "CORPORATE_ACTION_OR_PRICE_BASIS_CHANGE", "QUOTE_STALE", "TREND_INVALIDATED")
    limitations: tuple[str, ...] = ("NOT_INTRINSIC_VALUE", "NOT_EXECUTABLE_LIMIT", "CURRENT_AND_ADJUSTED_PRICE_BASES_NOT_CERTIFIED_IDENTICAL")
    executable_limit: None = None

    @model_validator(mode="after")
    def coherent(self) -> ResearchPricePlan:
        if self.lower > self.upper or self.observed_at > self.analysis_cutoff:
            raise ValueError("RESEARCH_PRICE_RANGE_OR_TIME_INVALID")
        if any(not v.is_finite() for v in self.measurement.values()):
            raise ValueError("RESEARCH_PRICE_NONFINITE_INPUT")
        return self


class ResearchRecommendation(StableModel):
    version: Literal["research-recommendation.v1"] = "research-recommendation.v1"
    symbol: str
    company_name: str | None = None
    company_name_source: str | None = None
    observed_reference: dict | None = None
    public_diagnostics: dict = Field(default_factory=dict)
    analysis_cutoff: AwareDatetime
    engine: str
    engine_hash: str
    snapshot_hash: str
    certification: str
    category: Category
    state: AdviceState
    score: Decimal | None
    rank: int | None
    factor_attribution: tuple[dict, ...]
    historical_risk: dict
    regime: dict | None
    desired_weight: Decimal | None
    feasible_weight: Decimal | None
    cost_adjusted_weight: Decimal | None
    current_weight: Decimal | None = None
    actual_eligible_change: None = None
    account_context: Literal["NOT_SUPPLIED_OR_NOT_VALIDATED", "AUTHORIZED_PAPER_RESEARCH"] = "NOT_SUPPLIED_OR_NOT_VALIDATED"
    price_plan: ResearchPricePlan | None
    evidence_ids: tuple[str, ...]
    gpt_interpretation: dict | None = None
    quant_gpt_conflict: bool = False
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    cost_assumptions: dict = Field(default_factory=dict)
    portfolio_concentration: dict = Field(default_factory=dict)
    important_unknowns: tuple[str, ...]
    next_inputs: tuple[str, ...]
    monitoring_triggers: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    explanation_zh: str
    expected_return: None = None
    predictive_confidence: None = None
    order_authorized: Literal[False] = False


@deterministic_decimal
def research_price_plan(feature: FeatureSnapshot, request: DailyResearchInput | None,
                        max_quote_age_seconds: int) -> ResearchPricePlan | None:
    if request is None or request.freshness_status != "PASS" or feature.quality_status == "REJECTED":
        return None
    observed = next((o for o in request.observations if o.ticker == feature.symbol), None)
    source = request.provider_provenance.get(feature.symbol)
    if not observed or not source or not 0 <= (request.analysis_cutoff - observed.observed_at).total_seconds() <= max_quote_age_seconds:
        return None
    if feature.as_of != request.analysis_cutoff or not feature.last_session:
        raise ValueError("RESEARCH_PRICE_FEATURE_CUTOFF_REQUIRED")
    if request.mode == "LIVE" and feature.synthetic:
        return None
    sma, atr = feature.value("sma20"), feature.value("atr14")
    if sma is None or atr is None or not sma.is_finite() or not atr.is_finite() or sma <= atr / 2 or atr <= 0:
        return None
    # A measured medium-term pullback band, not a discount applied to last price.
    lower, upper = sma - atr / 2, sma + atr / 2
    return ResearchPricePlan(symbol=feature.symbol, analysis_cutoff=request.analysis_cutoff,
        observed_price=observed.price, observed_at=observed.observed_at, source=source,
        quote_evidence_id=observed.reference, feature_input_hash=feature.input_hash,
        feature_session=feature.last_session.isoformat(), lower=lower, upper=upper,
        measurement={"sma20": sma, "atr14": atr},
        assessment="ABOVE_ZONE" if observed.price > upper else "BELOW_ZONE_REVIEW" if observed.price < lower else "IN_ZONE")


@deterministic_decimal
def build_recommendations(snapshot: QuantTerminalSnapshot, *, request: DailyResearchInput | None = None,
                          model_result: NativeResearchResult | None = None,
                          current: dict[str, Decimal] | None = None) -> tuple[ResearchRecommendation, ...]:
    """Account-free attraction first; target deltas require separately validated context.

    Callers may supply current only from a successful sanctioned portfolio view.
    Research states can never grant ticket authority. Model output is explanatory.
    """
    from meridian.config import load_policies
    from meridian.runtime import policy_directory
    if request and request.analysis_cutoff != snapshot.analysis_cutoff:
        raise ValueError("RECOMMENDATION_SHARED_CUTOFF_REQUIRED")
    if model_result:
        from meridian.terminal_service import terminal_model_context
        view = terminal_model_context(snapshot)['quant_terminal_view']
        expected = {r['signal']['evidence_id']: {'signal': r['signal'], 'quant': r['quant'],
            'certification': view['certification'], 'financial_oos_eligible': False,
            **({'desired_weight': r['desired_weight'], 'feasible_weight': r['feasible_weight'],
                'portfolio_assumption': view['portfolio_assumption']} if snapshot.engine == 'V2.3_SHADOW' else {})} for r in view['rows']}
        supplied = [e for e in model_result.evidence if e.source == snapshot.engine + '_TERMINAL']
        if len(supplied) != len(expected) or {e.evidence_id for e in supplied} != expected.keys() or any(
                e.observed_at != snapshot.analysis_cutoff or e.structured_value != expected[e.evidence_id] for e in supplied):
            raise ValueError('RECOMMENDATION_MODEL_EVIDENCE_BINDING_REQUIRED')
    if current is not None and (any(not v.is_finite() or v < 0 for v in current.values()) or sum(current.values(), D(0)) > 1):
        raise ValueError("RECOMMENDATION_INVALID_CURRENT_WEIGHTS")
    packet = snapshot.packet
    flagship = snapshot.flagship
    raw = {r.symbol: r for r in packet.symbols} if packet else {}
    v23scores = {s.bridge.symbol: s for s in flagship.scores} if flagship else {}
    allocation = flagship.allocation.allocation if flagship else packet.allocation if packet else None
    preferred = weights(allocation.preferred_target) if allocation else {}
    feasible = weights(allocation.feasible_target) if allocation else {}
    adjusted = weights(flagship.cost_adjusted_proposal.target) if flagship else {}
    max_age = load_policies(policy_directory()).data.quote_max_age_seconds
    results = []
    for row in snapshot.rows:
        entry = raw.get(row.symbol)
        score = v23scores.get(row.symbol) if flagship else entry.score if entry else None
        feature = entry.feature.base if entry else None
        plan = research_price_plan(feature, request, max_age) if feature else None
        weight = current.get(row.symbol, D(0)) if current is not None else None
        blockers = ["EXECUTION_QUOTES_AND_MANUAL_REVIEW_REQUIRED", "SHADOW_STRATEGY_NOT_PROMOTED"]
        if current is None:
            blockers.append("FRESH_AUTHORIZED_ACCOUNT_REQUIRED_FOR_SIZING")
        if not plan:
            blockers.append("PRICE_PLAN_REQUIRES_FRESH_OBSERVATION_AND_QUALIFIED_ATR_SMA")
        reasons = list(row.reasons)
        if not row.eligible:
            category: Category = "WAIT_FOR_EVIDENCE" if snapshot.status == "BLOCKED" else "NO_ACTION"
            reasons.append("UNQUALIFIED_HISTORY_NO_CERTIFIED_SIGNAL" if snapshot.status == "BLOCKED" else "SIGNAL_EXCLUDED_BY_QUANT_POLICY")
        elif feasible.get(row.symbol, D(0)) == 0:
            category = "EXIT_REVIEW" if weight and weight > 0 else "NO_ACTION"
            reasons.append("NO_FEASIBLE_RISK_BUDGET")
        elif weight is not None and weight > feasible[row.symbol]:
            category = "TRIM_CANDIDATE"
            reasons.append("CURRENT_EXPOSURE_ABOVE_SHADOW_TARGET")
        elif weight is not None and abs(weight - feasible[row.symbol]) <= D(".01"):
            category = "HOLD"
            reasons.append("WITHIN_RESEARCH_NO_TRADE_BAND")
        else:
            category = "ACCUMULATE_CONDITIONALLY" if plan else "BUY_CANDIDATE"
            reasons.append("ELIGIBLE_MULTI_HORIZON_SIGNAL_WITH_FEASIBLE_RISK_BUDGET")
        interpretation = None
        conflict = False
        if model_result:
            interpretation = {"status": model_result.research_state.value,
                "primary": model_result.primary.model_dump(mode="json") if model_result.primary else None,
                "skeptic": model_result.skeptic.model_dump(mode="json") if model_result.skeptic else None,
                "synthesis": model_result.synthesis.model_dump(mode="json", exclude={'confidence', 'bull_probability', 'base_probability', 'bear_probability'}) if model_result.synthesis else None,
                "scope": "UNIVERSE_RESEARCH_NOT_SYMBOL_SPECIFIC", "errors": model_result.degradation_reasons}
            conflict = bool(row.eligible and model_result.primary and model_result.primary.direction == "BEARISH")
            if conflict:
                reasons.append("QUANT_GPT_DISAGREEMENT_REQUIRES_THESIS_REVIEW")
            if model_result.missing_stages:
                reasons.append("GPT_INCOMPLETE_QUANT_PRESERVED")
        next_inputs = ["新鲜且授权的 Schwab-Paper 账户快照", "认证执行报价及独立人工审核"]
        if snapshot.status == "BLOCKED":
            next_inputs.append("带可得时间、复权和企业行动证明的历史序列与 SPY 基准")
        if not plan:
            next_inputs.append("带来源与观测时间的价格，以及合格 ATR14/SMA20")
        unknowns = ["EXPECTED_RETURN_UNCALIBRATED", "SECTOR_ETF_LOOKTHROUGH_NOT_INFERRED", "COMPANY_NAME_UNVERIFIED",
                    "GPT_NOT_RUN" if model_result is None else "GPT_INTERPRETATION_IS_NOT_FINANCIAL_AUTHORITY"]
        if snapshot.certification == "SYNTHETIC_DIAGNOSTIC":
            unknowns.append("SYNTHETIC_DIAGNOSTIC_NOT_LIVE_RECOMMENDATION")
        evidence_ids = (row.evidence_id, *((plan.quote_evidence_id,) if plan else ()))
        observation = next((o for o in request.observations if o.ticker == row.symbol), None) if request else None
        source = request.provider_provenance.get(row.symbol) if request else None
        observed_reference = None
        if request and observation and source and request.freshness_status == 'PASS' and 0 <= (snapshot.analysis_cutoff - observation.observed_at).total_seconds() <= max_age:
            observed_reference = {'price': str(observation.price), 'observed_at': observation.observed_at.isoformat(),
                'source': source, 'evidence_id': observation.reference, 'certification': 'PUBLIC_RESEARCH_UNVERIFIED'}
            evidence_ids = tuple(dict.fromkeys((*evidence_ids, observation.reference)))
        from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityIdentityUnavailable
        company_name = None
        try:
            company_name = DEFAULT_SECURITY_MASTER.resolve(row.symbol).legal_name
        except SecurityIdentityUnavailable:
            pass
        risk_values = {name: feature.value(name) for name in ("volatility_20", "volatility_60", "downside_deviation", "drawdown_60", "beta_60", "dollar_volume_20")} if feature else {}
        results.append(ResearchRecommendation(symbol=row.symbol, company_name=company_name,
            company_name_source='CURRENT_SECURITY_MASTER_NOT_HISTORICAL_MEMBERSHIP' if company_name else None,
            observed_reference=observed_reference, public_diagnostics=snapshot.public_diagnostics.get(row.symbol, {}),
            analysis_cutoff=snapshot.analysis_cutoff,
            engine=snapshot.engine, engine_hash=snapshot.engine_hash, snapshot_hash=snapshot.digest,
            certification=snapshot.certification, category=category,
            state="BLOCKED" if snapshot.status == "BLOCKED" else "CONDITIONAL_PLAN" if plan and row.eligible else "RESEARCH_ONLY",
            score=row.score, rank=row.rank, factor_attribution=tuple(c.model_dump(mode="json") for c in score.factor_attribution) if score else (),
            historical_risk=risk_values, regime=packet.regime.model_dump(mode="json") if packet else None,
            desired_weight=preferred.get(row.symbol) if allocation else None,
            feasible_weight=feasible.get(row.symbol, D(0)) if allocation else None,
            cost_adjusted_weight=adjusted.get(row.symbol, D(0)) if flagship else None,
            current_weight=weight, account_context="AUTHORIZED_PAPER_RESEARCH" if current is not None else "NOT_SUPPLIED_OR_NOT_VALIDATED",
            price_plan=plan, evidence_ids=evidence_ids, gpt_interpretation=interpretation, quant_gpt_conflict=conflict,
            reasons=tuple(reasons), blockers=tuple(blockers), important_unknowns=tuple(unknowns), next_inputs=tuple(next_inputs),
            cost_assumptions={**(packet.cost_assumptions.model_dump(mode='json') if packet else {}),
                'monetary_cost': None, 'basis': 'NO_ACCOUNT_NORMALIZED_RESEARCH_NOT_ACCOUNT_COST', 'spread_observed': False},
            portfolio_concentration=allocation.risk.model_dump(mode='json') if allocation else {},
            monitoring_triggers=("下一完整交易日重算动量、趋势及风险预算", "价格进入测量区间后核实流动性、企业行动与反方证据"),
            invalidation_conditions=("绝对动量转弱或趋势失稳", "市场风险预算收缩", "数据过期、复权变化或投资假设被新证据否定"),
            explanation_zh=("关注依据：合格多周期因子与约束组合均支持研究。" if row.eligible else "未形成可用候选：" + "、".join(reasons))
                + (" 当前没有账户，不推断持仓、现金或份额。" if current is None else " 持仓与目标仅作隔离研究比较。")
                + (" 研究价位基于 SMA20 与 ATR14，必须核实价格口径，不能直接下单。" if plan else " 尚无合格价格计划，先补齐具体证据。")))
    return tuple(results)
