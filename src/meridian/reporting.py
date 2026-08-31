# pyright: reportRedeclaration=false
"""Shared Markdown and JSON reporting for manual review."""

from __future__ import annotations

from meridian.pipeline import ResearchPipelineResult
from meridian.schemas import DailyDecision, RunStatus


def report_json(decision: DailyDecision) -> str:
    return decision.stable_json()


def report_markdown(decision: DailyDecision) -> str:
    lines = [
        "# MERIDIAN ALPHA",
        "",
        "## Daily Decision",
        "",
        f"- As of: {decision.as_of.isoformat()}",
        f"- Status: **{decision.overall_status}**",
        f"- Account freshness: {decision.account_snapshot_status}",
        f"- Market freshness: {decision.market_data_status}",
        f"- Risk regime: {decision.regime}",
        "",
    ]
    if decision.target_portfolio is not None:
        lines.extend(
            [
                "## Target Portfolio",
                "",
                "| Ticker | Target Weight | Conviction |",
                "| --- | ---: | ---: |",
            ]
        )
        lines.extend(
            f"| {position.ticker} | {position.target_weight:.2%} | {position.conviction:.2%} |"
            for position in decision.target_portfolio.positions
        )
        lines.append(f"| CASH | {decision.target_portfolio.cash_weight:.2%} | — |")
        lines.append("")
    ticket_title = (
        "## Manual Order Ticket"
        if decision.overall_status is RunStatus.READY_FOR_MANUAL_ENTRY
        else "## DRAFT — DO NOT ENTER"
    )
    lines.extend(
        [
            ticket_title,
            "",
            "| Ticker | Side | Shares | Preferred Limit | Notional | Current / Target | TIF | Reason |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| {order.ticker} | {order.side} | {order.quantity} | {order.preferred_limit or '—'} | {order.estimated_notional} | {order.current_weight:.2%} / {order.target_weight:.2%} | {order.time_in_force} | {order.reason} |"
        for order in decision.orders
    )
    lines.extend(["", "**DO NOT CHASE.** Recalculate if account or market freshness changes."])
    if decision.warnings or decision.blocked_reasons:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in (*decision.warnings, *decision.blocked_reasons))
    return "\n".join(lines)


def research_report_markdown(result: ResearchPipelineResult) -> str:
    """Render research context without promoting graph ratings to recommendations."""
    lines = [
        "# MERIDIAN ALPHA",
        "",
        "## QUANT SCREEN",
        "",
        f"- As of: {result.as_of.isoformat()}",
        f"- Mode: {result.mode}",
        f"- Pipeline status: {result.status}",
        f"- Synthetic/test data: {'YES' if result.synthetic else 'NO'}",
        "",
        "| Rank | Ticker | Quant score | Held | Decision |",
        "| ---: | --- | ---: | :---: | --- |",
    ]
    lines.extend(
        f"| {candidate.rank} | {candidate.ticker} | {candidate.quant_score} | "
        f"{'YES' if candidate.is_existing_holding else 'NO'} | SELECTED |"
        for candidate in result.candidate_set.candidates
    )
    lines.extend(
        f"| {candidate.rank} | {candidate.ticker} | {candidate.quant_score} | "
        f"{'YES' if candidate.is_existing_holding else 'NO'} | "
        f"DEFERRED: {candidate.deferred_reason or 'UNSPECIFIED'} |"
        for candidate in result.candidate_set.deferred
    )
    lines.extend(["", "## TRADINGAGENTS GRAPH SUMMARY", ""])
    if result.graph_summaries:
        lines.extend(
            f"- {summary.ticker}: graph rating={summary.graph_rating or 'UNAVAILABLE'} "
            f"(diagnostic only); reports={', '.join(summary.reports_present) or 'none'}; "
            f"status={summary.status}"
            for summary in result.graph_summaries
        )
    else:
        lines.append("- No graph summary available.")
    lines.extend(["", "## MERIDIAN EVIDENCE", ""])
    if result.evidence_packets:
        for packet in result.evidence_packets:
            lines.append(
                f"- {packet.ticker}: {len(packet.items)} items; "
                f"point-in-time={packet.point_in_time_status}; "
                f"provider statuses={', '.join(packet.provider_statuses) or 'none'}"
            )
            lines.extend(f"  - evidence_id: {item.stable_id}" for item in packet.items)
    else:
        lines.append("- No evidence packet available.")
    lines.extend(["", "## GROUNDED RESEARCH SIGNAL", ""])
    if result.agent_signals:
        lines.extend(
            f"- {signal.ticker}: {signal.direction}, conviction={signal.conviction}; "
            f"cited evidence={', '.join(item.stable_id for item in signal.signal.evidence)}"
            for signal in result.agent_signals
        )
    else:
        lines.append("RESEARCH NOT GROUNDED")
        lines.append("No validated Meridian AgentSignal was created.")
    if result.warnings:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in result.warnings]])
    return "\n".join(lines)


def mobile_daily_summary(decision: DailyDecision) -> dict[str, object]:
    """Return a compact Chinese host-rendering contract without execution claims."""
    label = {
        RunStatus.READY_FOR_MANUAL_ENTRY: "可手动录入",
        RunStatus.DRAFT: "草稿",
        RunStatus.ANALYSIS_ONLY: "建议",
    }.get(decision.overall_status, "已阻塞")
    return {
        "今日状态": label,
        "账户概览": {
            "同步": decision.account_sync_state.value,
            "新鲜度": decision.account_snapshot_status.value,
        },
        "市场环境": {"新鲜度": decision.market_data_status.value, "regime": decision.regime},
        "Quant 判断": "确定性量化/风控结果；不代表成交。",
        "AI 研判": "仅限已认证证据的 Shadow 研判。",
        "抄底观察": "仅研究观察；不可直接决定仓位或订单。",
        "证据": "证据授权与 PIT 状态见运行报告。",
        "风险": list(decision.blocked_reasons),
        "目标组合": [
            {"ticker": position.ticker, "target_weight": str(position.target_weight)}
            for position in (decision.target_portfolio.positions if decision.target_portfolio else ())
        ],
        "操作清单": [
            {"ticker": order.ticker, "side": order.side.value, "status": order.status.value}
            for order in decision.orders
        ],
        "当前阻塞项": list(decision.blocked_reasons),
        "执行状态": "未执行；仅后续新账户快照可证明成交",
    }

def mobile_daily_report_v3(decision: DailyDecision, *, profile: str = "SHADOW_LIVE", blockers: tuple[str, ...] = ()) -> str:
    """Concise mobile Chinese daily report with one explicit top-level status."""
    from meridian.profiles import RuntimeProfile, report_status_for
    try:
        selected = RuntimeProfile(profile.upper())
    except ValueError:
        selected = RuntimeProfile.SHADOW_LIVE
    status = report_status_for(selected, decision).value
    holdings = ", ".join(
        f"{position.ticker} {position.target_weight:.1%}"
        for position in (decision.target_portfolio.positions if decision.target_portfolio else ())
    ) or "现金为主"
    lines = [
        f"【今日状态】{status}",
        f"【账户】同步={decision.account_sync_state.value}；新鲜度={decision.account_snapshot_status.value}",
        f"【市场】regime={decision.regime}；新鲜度={decision.market_data_status.value}",
        "【Quant】确定性量化结果；目标权重由系统计算。",
        "【AI基本面】仅展示已认证证据支持的方向与置信度。",
        "【抄底观察】仅影子研究，不代表交易。",
        f"【组合】{holdings}；现金={decision.target_portfolio.cash_weight:.1%}" if decision.target_portfolio else "【组合】未生成目标组合",
        "【操作草稿】未执行；没有经认证报价时不可生成手动入口草稿。",
        f"【风险/阻塞】{'; '.join((*decision.blocked_reasons, *blockers)) or '无额外阻塞'}",
    ]
    return "\n".join(lines)


_previous_report_markdown = report_markdown


def report_markdown(decision: DailyDecision, *, profile: str = "TEST", status: str | None = None) -> str:
    """Render the legacy report with a mandatory leading release status."""
    from meridian.profiles import RuntimeProfile, report_status_for
    try:
        selected = RuntimeProfile(profile.upper())
    except ValueError:
        selected = RuntimeProfile.TEST
    top = status or report_status_for(selected, decision).value
    return f"STATUS: **{top}**\n" + _previous_report_markdown(decision)
