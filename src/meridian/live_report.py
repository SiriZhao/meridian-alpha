"""Chinese research explanations derived from sealed evidence, with explicit gaps."""
from __future__ import annotations

from typing import Any

from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityIdentityUnavailable


def quant_research_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = report.get('quant_live', {})
    packet = snapshot.get('quant_packet') or {}
    quant = {r['symbol']: r for r in packet.get('symbols', [])}
    advice = {r['symbol']: r for r in report.get('decisions', [])}
    recommendations = {r['symbol']: r for r in report.get('research_recommendations', [])}
    rows = []
    for symbol, condition in snapshot.get('price_conditions', {}).items():
        market = report.get('market_snapshot', {}).get(symbol, {})
        q = quant.get(symbol, {})
        score = q.get('score') or {}
        verified = snapshot.get('strict_status') == 'VERIFIED_RESEARCH_AVAILABLE'
        provisional = snapshot.get('provisional_diagnostics', {}).get(symbol, {})
        factors = q.get('feature', {}).get('base', {}).get('factors', [])
        values = {f['name']: f['raw_value'] for f in factors}
        try:
            company = DEFAULT_SECURITY_MASTER.resolve(symbol).legal_name
        except SecurityIdentityUnavailable:
            company = None
        fresh = market.get('freshness') in {'LIVE', 'DELAYED'}
        recommendation = recommendations.get(symbol, {})
        category = recommendation.get('category', advice.get(symbol, {}).get('decision_category', 'WAIT_FOR_EVIDENCE'))
        reasons = list(q.get('reasons_for_waiting', [])) + list(provisional.get('reasons', []))
        if not verified:
            reasons.append('INSUFFICIENT_VERIFIED_HISTORY')
        if not fresh:
            reasons.append('CURRENT_PRICE_UNAVAILABLE_OR_STALE')
        rows.append({'symbol': symbol, 'company': company or 'UNKNOWN（名称未获核验）',
            'observed_price': market.get('current_price') if fresh else None,
            'dated_reference_price': market.get('reference_price', market.get('last')),
            'observation_at': market.get('timestamp'), 'timezone': 'America/New_York',
            'provider': market.get('provider', market.get('source')), 'feed_delay_seconds': market.get('declared_delay_seconds'),
            'history_quality': snapshot.get('strict_status'),
            'momentum_3m': values.get('momentum_3m'), 'momentum_6m': values.get('momentum_6m'),
            'relative_strength_6m': values.get('relative_momentum_6m'),
            'trend_sma60': values.get('sma60'), 'volatility_60': values.get('volatility_60'),
            'drawdown_252': values.get('drawdown_252'),
            'quant_score': recommendation.get('score') if recommendation else score.get('signal_strength') if verified else None,
            'quant_rank': recommendation.get('rank') if recommendation else score.get('bridge', {}).get('relative_rank') if verified and not score.get('bridge', {}).get('exclusion_reasons') else None,
            'factor_attribution': recommendation.get('factor_attribution', score.get('factor_attribution', [])),
            'signal_persistence': score.get('positive_observations') if verified else None,
            'regime': packet.get('regime'), 'regime_is_prediction': False,
            'preferred_exposure': recommendation.get('desired_weight', q.get('preferred_exposure')),
            'feasible_exposure': recommendation.get('feasible_weight', q.get('feasible_exposure')),
            'current_exposure': q.get('current_exposure'), 'cost_adjusted_exposure': q.get('cost_adjusted_exposure'),
            'concentration_effect': packet.get('constraint_modifications', []),
            'decision_category': category, 'price_condition': condition,
            'catalysts': 'UNKNOWN：未提供带来源与时间的新闻或财务证据。',
            'gpt_interpretation': advice.get(symbol, {}).get('thesis', 'UNKNOWN：模型未完成，保留定量证据。'),
            'scenarios': report.get('research_summary', {}).get('scenarios') or 'UNKNOWN：没有已验证的模型情景输出。',
            'opposing_evidence': advice.get(symbol, {}).get('negative_drivers', []) or reasons,
            'monitoring_trigger': advice.get(symbol, {}).get('wait_until') or '等待新鲜报价、可信复权历史与企业行动证据；按同一截止时点重新计算。',
            'invalidation_condition': condition.get('invalidation_condition'),
            'no_action_reasons': sorted(set(reasons)),
            'important_unknowns': ['内在价值', '新闻催化剂', '校准预期收益', 'ETF 穿透重叠', '当前账户风险上下文'],
            'manual_requirements': ['这是研究分类，不是券商订单。', '独立核对账户、报价和风险；真实订单逐笔人工批准。'],
            'research_recommendation': recommendation or None,
            'quant_engine': snapshot.get('engine', 'V2.2_SHADOW'), 'gpt_engine': 'GPT_ADVISORY',
            'predictive_confidence': None, 'trade_authorized': False,
            'explanation': f"{symbol}：定量通道为 {snapshot.get('strict_status')}；"
                f"当前报价状态 {market.get('freshness', 'UNKNOWN')}；研究分类 {category}。"
                '缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。'})
    return rows


def render_quant_research(report: dict[str, Any]) -> str:
    lines = ['## Quant 与 GPT 决策来源', '',
        'QUANT_V1_BASELINE：原 canonical 默认；本报告的旧目标只是 live 参考比较。',
        f"{report.get('quant_live', {}).get('engine', 'V2.2_SHADOW')}：确定性研究挑战者；GPT_ADVISORY：模型解释，无修改分数或交易授权。",
        f"共享分析截止时点：{report.get('quant_live', {}).get('analysis_cutoff', 'UNKNOWN')}",
        f"证据指纹：{report.get('quant_live_hash', 'UNKNOWN')}", '', '## 中文研究观察', '']
    for row in quant_research_rows(report):
        lines += [f"### {row['company']} / {row['symbol']}", '', row['explanation'], '',
            f"当前观察价：{row['observed_price']}；带日期参考价：{row['dated_reference_price']}；"
            f"时间：{row['observation_at']}；来源：{row['provider']}；声明延迟：{row['feed_delay_seconds']}。", '',
            f"Quant 排名：{row['quant_rank']}；动量：{row['momentum_6m']}；相对强弱：{row['relative_strength_6m']}；波动：{row['volatility_60']}。",
            '研究分类：' + row['decision_category'],
            'GPT 解读：' + row['gpt_interpretation'],
            '反方/缺口：' + '、'.join(row['no_action_reasons']),
            '下一步：' + '；'.join((row.get('research_recommendation') or {}).get('next_inputs', [row['monitoring_trigger']])), '']
    return '\n'.join(lines)
