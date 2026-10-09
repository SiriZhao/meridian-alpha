"""Deterministic report assembly keeps observed, computed and model claims separate."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, Field

from meridian.daily_research import DailyResearchInput
from meridian.gpt_native_research import NativeResearchResult
from meridian.research_order_review import ManualOrderTicket
from meridian.research_recommendations import ResearchRecommendation, build_recommendations
from meridian.schemas import StableModel
from meridian.terminal_service import TerminalBrief, research_quality_scorecard


class ObservedResearchPrice(StableModel):
    symbol: str
    price: str
    observed_at: AwareDatetime
    source: str
    evidence_id: str
    freshness: Literal["AS_OF_INPUT_CUTOFF", "STALE_OR_UNKNOWN"]
    certification: Literal["PUBLIC_RESEARCH_UNVERIFIED"] = "PUBLIC_RESEARCH_UNVERIFIED"


class DecisionBrief(StableModel):
    manual_ticket: ManualOrderTicket | None = None
    model_trace: dict | None = None
    recommendations: tuple[ResearchRecommendation, ...] = ()
    recommendation_contract: Literal["research-recommendation.v1"] = "research-recommendation.v1"
    version: Literal["meridian-decision-brief.v1"] = "meridian-decision-brief.v1"
    analysis_cutoff: AwareDatetime
    data_mode: Literal["LIVE", "FIXTURE", "REPLAY", "UNKNOWN"]
    quant_snapshot_hash: str
    observed_facts: tuple[ObservedResearchPrice, ...] = Field(max_length=8)
    deterministic_quant_analysis: dict
    gpt_interpretation: dict | None
    conditional_forecast: dict | None
    risk_constraints: dict
    unknown_information: tuple[str, ...]
    possible_manual_action: None = None
    reason_for_waiting: str
    quality_scorecard: dict | None
    execution_authority: Literal["NONE"] = "NONE"


def generate_decision_brief(terminal: TerminalBrief, *, request: DailyResearchInput | None = None,
                            model_result: NativeResearchResult | None = None,
                            paper_review: ManualOrderTicket | None = None) -> DecisionBrief:
    cutoff = terminal.quant.analysis_cutoff
    if request and request.analysis_cutoff != cutoff:
        raise ValueError("DECISION_BRIEF_SHARED_CUTOFF_REQUIRED")
    if paper_review and (paper_review.analysis_cutoff != cutoff or paper_review.request_hash != terminal.quant.request_hash or terminal.quant.engine != 'V2.3_SHADOW'):
        raise ValueError('DECISION_BRIEF_PAPER_PLAN_CUTOFF_OR_INPUT_MISMATCH')
    prices = []
    if request:
        from meridian.config import load_policies
        from meridian.runtime import policy_directory
        max_age = load_policies(policy_directory()).data.quote_max_age_seconds
        for observed in request.observations:
            age = (cutoff - observed.observed_at).total_seconds()
            if age < 0:
                raise ValueError("DECISION_BRIEF_OBSERVATION_AFTER_CUTOFF")
            source = request.provider_provenance.get(observed.ticker)
            if request.freshness_status != "PASS" or age > max_age or not source:
                # No current price claim survives a stale/missing-source gate.
                continue
            prices.append(ObservedResearchPrice(symbol=observed.ticker, price=str(observed.price),
                observed_at=observed.observed_at, source=source, evidence_id=observed.reference,
                freshness="AS_OF_INPUT_CUTOFF"))
    interpretation: dict[str, Any] | None = None
    forecast: dict[str, Any] | None = None
    scorecard = None
    unknowns = ["EXPECTED_RETURN_UNCALIBRATED", "EXECUTION_QUOTES_AND_MANUAL_REVIEW_REQUIRED"]
    if not prices:
        unknowns.append("CURRENT_PRICE_UNAVAILABLE_OR_STALE")
    if model_result:
        catalog = {r.evidence_id for r in terminal.quant.rows}
        model_source = terminal.quant.engine + "_TERMINAL"
        model_ids = {e.evidence_id for e in model_result.evidence if e.source == model_source}
        if model_ids != catalog or any(e.observed_at != cutoff for e in model_result.evidence if e.source == model_source):
            raise ValueError("DECISION_BRIEF_MODEL_EVIDENCE_IDENTITY_MISMATCH")
        from meridian.terminal_service import terminal_model_context
        view = terminal_model_context(terminal.quant)["quant_terminal_view"]
        expected = {r["signal"]["evidence_id"]: {"signal": r["signal"], "quant": r["quant"],
            "certification": view["certification"], "financial_oos_eligible": False,
            **({"desired_weight": r["desired_weight"], "feasible_weight": r["feasible_weight"],
                "portfolio_assumption": view["portfolio_assumption"]} if terminal.quant.engine == "V2.3_SHADOW" else {})} for r in view["rows"]}
        if any(e.structured_value != expected[e.evidence_id] for e in model_result.evidence if e.source == model_source):
            raise ValueError("DECISION_BRIEF_MODEL_NUMERICAL_EVIDENCE_MISMATCH")
        interpretation = {"status": model_result.research_state.value,
            "primary": model_result.primary.model_dump(mode="json") if model_result.primary else None,
            "skeptic": model_result.skeptic.model_dump(mode="json") if model_result.skeptic else None,
            "disagreement_score": model_result.disagreement_score,
            "errors": list(model_result.degradation_reasons)}
        if model_result.scenarios:
            forecast = {name: {"description": getattr(model_result.scenarios, name).description,
                "assumptions": list(getattr(model_result.scenarios, name).key_assumptions),
                "invalidators": list(getattr(model_result.scenarios, name).invalidators)} for name in ("bull", "base", "bear")}
            forecast["probabilities"] = None
            forecast["calibration"] = "UNCALIBRATED"
        scorecard = research_quality_scorecard(model_result)
    else:
        unknowns.append("GPT_NOT_RUN")
    recommendations = build_recommendations(terminal.quant, request=request, model_result=model_result,
        current=terminal.portfolio.current if terminal.portfolio and terminal.portfolio.status != "BLOCKED" else None)
    trace = None
    if model_result:
        import hashlib
        trace = {'run_id': model_result.run_id, 'input_view_hash': terminal_model_context(terminal.quant)['quant_terminal_view_hash'],
            'request_hash': request.input_hash if request else None,
            'data_mode': request.mode if request else 'UNKNOWN', 'actual_model_call_verified': False,
            'stages': {name: {'status': stage.status.value, 'model': stage.model, 'reasoning_effort': stage.reasoning_effort,
                'duration_ms': stage.duration_ms, 'error_type': stage.error_type,
                'output_hash': hashlib.sha256(stage.stable_json().encode()).hexdigest()} for name, stage in model_result.stages.items()}}
    return DecisionBrief(recommendations=recommendations, model_trace=trace, manual_ticket=paper_review,
        analysis_cutoff=cutoff, data_mode=request.mode if request else "UNKNOWN", quant_snapshot_hash=terminal.quant.digest,
        observed_facts=tuple(prices), deterministic_quant_analysis=terminal.views["QUANT_EXPLORER"],
        gpt_interpretation=interpretation, conditional_forecast=forecast,
        risk_constraints=terminal.views["PORTFOLIO_RISK"], unknown_information=tuple(unknowns),
        reason_for_waiting="研究结果未授权交易；缺失的新鲜执行报价、账户或证据必须先补齐，等待是有效选择。",
        quality_scorecard=scorecard)


def render_decision_brief(brief: DecisionBrief) -> str:
    """Human-facing summary; full structured proof remains in JSON."""
    lines = ['# Meridian 中文决策研究', '', f'分析时点：{brief.analysis_cutoff.isoformat()}；数据模式：{brief.data_mode}',
        '研究评级不等于订单许可；自动交易禁用。', '', '## 市场综述与数据健康', '',
        '数据缺口：' + '、'.join(brief.unknown_information), '', '## 今日值得研究的标的', '']
    for r in sorted(brief.recommendations, key=lambda r: (r.rank is None, r.rank or 0, r.symbol)):
        lines.extend([f'### {r.symbol} — {r.category} / {r.state}', '', r.explanation_zh,
            f'Quant：{r.engine}；排名：{r.rank}；评分：{r.score}；证据等级：{r.certification}。',
            f'仓位偏好：{r.desired_weight}；风险可行目标：{r.feasible_weight}；成本调整参考：{r.cost_adjusted_weight}；当前持仓：{r.current_weight}。',
            '这些权重是影子研究目标，未证明净预期收益。'])
        if r.price_plan:
            p = r.price_plan
            lines.extend([f'条件价位：[{p.lower}, {p.upper}]（SMA20 ± ATR14/2，复权历史研究口径）。',
                f'观察价：{p.observed_price}；来源：{p.source}；时点：{p.observed_at.isoformat()}；区间状态：{p.assessment}。',
                '行动前条件：核实价格口径、企业行动、流动性、账户与认证执行报价；区间不代表内在价值或可执行限价。'])
        if r.gpt_interpretation:
            gpt = r.gpt_interpretation
            lines.extend(['GPT 研究状态：' + gpt['status'],
                '看多/中性/看空论证：' + str((gpt.get('primary') or {}).get('thesis', '模型未完成')),
                '反方观点：' + '；'.join((gpt.get('skeptic') or {}).get('challenges', [])),
                'Quant/GPT 冲突：' + ('存在，保留双方观点并等待复核。' if r.quant_gpt_conflict else '未检测到已提供论证之间的方向冲突。')])
        else:
            lines.append('GPT 未运行；不补写催化剂、估值或模型结论。')
        lines.extend(['不应操作的条件：' + '；'.join(r.invalidation_conditions),
            '阻塞原因：' + '、'.join(r.blockers), '下一步：' + '；'.join(r.next_inputs),
            '证据 ID：' + '、'.join(r.evidence_ids), ''])
    lines.extend(['## 风险与人工审核', '', brief.reason_for_waiting,
        'V1 canonical、真实账户与 Paper Ledger 未因本研究报告改变；金融 Alpha 尚未证明。'])
    if brief.manual_ticket:
        ticket = brief.manual_ticket
        lines.extend(['', f'隔离 Paper 规划：{ticket.planning_status} / {ticket.state}；草稿数：{len(ticket.paper_drafts)}；成交数：0。',
            '人工挂单阻塞：' + '、'.join((*ticket.blockers, *ticket.manual_blockers)),
            '草稿价格来自原 OrderPlanner 的认证报价管线，未使用研究区间代替限价。'])
    return '\n'.join(lines) + '\n'
