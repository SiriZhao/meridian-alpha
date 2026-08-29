"""Offline/replay-first real-shaped shadow daily run.

This service intentionally uses synthetic/replay evidence and TEST-mode graph
fixtures.  It exercises candidate selection, packet construction, grounded
normalization and deterministic portfolio stages while mechanically keeping
all research non-executable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.allocation import DeterministicFallbackAllocator
from meridian.config import EvidenceCompletenessPolicy, EvidencePacketPolicy, ResearchBudgetPolicy
from meridian.evidence import EvidenceCompletenessEvaluator, EvidencePacketBuilder
from meridian.evidence_foundation import (
    ReplayFundamentalEvidenceProvider,
    ReplayMacroEvidenceProvider,
    ReplayNewsEvidenceProvider,
)
from meridian.pipeline import (
    FakeGraphResearchProvider,
    ResearchPipelineMode,
    ResearchPipelineService,
)
from meridian.reconciliation import ReconciliationEngine
from meridian.research import FakeGroundedResearchNormalizer, GroundedResearchStatus
from meridian.risk import RiskEngine
from meridian.schemas import AccountSnapshot, AccountSyncState, AlphaScore, FreshnessState


class ShadowCandidateDiagnostic(dict[str, Any]):
    pass


def _account(as_of: datetime) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="shadow-synthetic-50000",
        account_alias="shadow-synthetic",
        provider="manual-fixture",
        as_of=as_of,
        total_equity=Decimal("50000"),
        cash=Decimal("50000"),
        holdings=(),
        sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )


def run_shadow_daily(
    *,
    as_of: datetime | None = None,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    """Run a bounded synthetic daily analysis and write sanitized reports."""
    cutoff = as_of or datetime(2026, 8, 28, 20, 0, tzinfo=UTC)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("shadow as_of must be timezone-aware")
    tickers = ("AAPL", "MSFT", "NVDA", "SPY", "QQQ")
    budget = ResearchBudgetPolicy(
        max_graph_tickers_per_run=3,
        max_parallel_graphs=1,
        max_graph_age_hours=24,
        always_review_existing_holdings=True,
        candidate_selection_mode="existing_then_order",
        minimum_quant_score=Decimal("-1"),
        existing_holding_review_policy="always",
    )
    providers = (
        ReplayFundamentalEvidenceProvider(),
        ReplayNewsEvidenceProvider(),
        ReplayMacroEvidenceProvider(),
    )
    packet_builder = EvidencePacketBuilder(
        EvidencePacketPolicy(max_total_evidence_items=12, max_items_per_type=2, max_summary_characters_per_item=500),
        clock=lambda: cutoff,
    )
    # Build deterministic packets first so explicit fake citations resolve to
    # the exact packet the pipeline will construct.
    packet_by_ticker = {ticker: packet_builder.gather(ticker, cutoff, providers) for ticker in tickers}
    signals = {}
    for ticker, packet in packet_by_ticker.items():
        if packet.items:
            signals[ticker] = {
                "ticker": ticker,
                "as_of": cutoff,
                "direction": "BULLISH",
                "conviction": Decimal("0.60"),
                "thesis": "Synthetic shadow normalization only; not live research.",
                "risks": ("Synthetic evidence",),
                "cited_evidence_ids": (packet.items[0].stable_id,),
                "status": "AVAILABLE",
            }
    service = ResearchPipelineService(
        budget,
        graph_provider=FakeGraphResearchProvider(),
        evidence_builder=packet_builder,
        evidence_providers=providers,
        normalizer=FakeGroundedResearchNormalizer(signals, allow_synthetic=True),
        live_enabled=False,
    )
    features = {
        ticker: {"feature_timestamp": cutoff, "momentum": Decimal(str(index)) / Decimal("10"), "trend": Decimal("0.1")}
        for index, ticker in enumerate(tickers, start=1)
    }
    result = service.run(tickers, cutoff, features, mode=ResearchPipelineMode.TEST)
    completeness_policy = EvidenceCompletenessPolicy(
        minimum_total_items=1,
        minimum_distinct_sources=1,
        required_evidence_types=(),
        maximum_age_by_type={},
        minimum_point_in_time_quality=Decimal("1"),
    )
    diagnostics: list[ShadowCandidateDiagnostic] = []
    alpha_scores: list[AlphaScore] = []
    outcomes = {outcome.ticker: outcome for outcome in result.grounded_outcomes}
    packets = {packet.ticker: packet for packet in result.evidence_packets}
    for candidate in result.candidate_set.candidates:
        packet = packets.get(candidate.ticker)
        outcome = outcomes.get(candidate.ticker)
        completeness = EvidenceCompletenessEvaluator(completeness_policy).evaluate(packet, cutoff) if packet else None
        signal = outcome.signal if outcome and outcome.status is GroundedResearchStatus.AVAILABLE else None
        quant_score = candidate.quant_score
        alpha_scores.append(
            AlphaScore(
                ticker=candidate.ticker,
                score=quant_score,
                confidence=Decimal("0"),
                expected_direction="BULLISH" if quant_score > 0 else "NEUTRAL",
                risk_penalty=Decimal("0"),
                evidence_quality=Decimal("0"),
                model_source="deterministic-shadow-quant-only",
            )
        )
        diagnostics.append(
            ShadowCandidateDiagnostic(
                ticker=candidate.ticker,
                quant_only_score=str(quant_score),
                grounded_research_modifier="0",
                final_alpha=str(quant_score),
                evidence_completeness=(completeness.model_dump(mode="json") if completeness else None),
                evidence_sources=sorted({item.source for item in packet.items}) if packet else [],
                research_direction=signal.direction if signal else None,
                research_conviction=str(signal.conviction) if signal else None,
                risk_penalty="0",
                target_before_risk={},
                target_after_risk={},
                research_status=outcome.status.value if outcome else "UNAVAILABLE",
                research_executable=False,
            )
        )
    account = _account(cutoff)
    target = DeterministicFallbackAllocator().allocate(alpha_scores, {}, account, _risk_policy())
    risk = RiskEngine().approve(target, account, "RISK_ON", _risk_policy())
    reconciliation = ReconciliationEngine().reconcile(account, risk.approved)
    target_weights = {position.ticker: str(position.target_weight) for position in risk.approved.positions}
    for item in diagnostics:
        item["target_before_risk"] = {position.ticker: str(position.target_weight) for position in target.positions}
        item["target_after_risk"] = target_weights
    report: dict[str, Any] = {
        "schema_version": "1",
        "created_at": cutoff.isoformat(),
        "as_of": cutoff.isoformat(),
        "mode": "SHADOW",
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "account_source": "SYNTHETIC_MANUAL_FIXTURE",
        "security_master": "DEFAULT_VERIFIED_FIXTURE_ONLY",
        "candidate_selection": [candidate.model_dump(mode="json") for candidate in result.candidate_set.candidates],
        "deferred_candidates": [candidate.model_dump(mode="json") for candidate in result.candidate_set.deferred],
        "pipeline_status": result.status.value,
        "graph_summaries": [summary.model_dump(mode="json") for summary in result.graph_summaries],
        "evidence_packets": [packet.model_dump(mode="json") for packet in result.evidence_packets],
        "grounded_statuses": [outcome.status.value for outcome in result.grounded_outcomes],
        "diagnostics": diagnostics,
        "certified_signal_count": len(result.agent_signals),
        "abstain_count": sum(1 for outcome in result.grounded_outcomes if outcome.status is not GroundedResearchStatus.AVAILABLE),
        "non_executable_grounded_count": sum(1 for outcome in result.grounded_outcomes if outcome.status is GroundedResearchStatus.AVAILABLE),
        "blocked_non_executable_count": sum(1 for outcome in result.grounded_outcomes if outcome.status is GroundedResearchStatus.AVAILABLE),
        "provider_failures": [warning for warning in result.warnings if "FAIL" in warning or "ERROR" in warning],
        "allocator": {"name": target.allocator_name, "positions": target_weights},
        "risk_violations": list(risk.violations),
        "reconciliation_status": reconciliation.status.value,
        "content_hash": hashlib.sha256(json.dumps(result.model_dump(mode="json"), sort_keys=True, default=str).encode()).hexdigest(),
        "warnings": ["SYNTHETIC - NOT LIVE DATA", "SHADOW / NOT AUTHORIZED FOR ENTRY"],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    if output_markdown is not None:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_markdown(report), encoding="utf-8")
    return report


def _risk_policy() -> Any:
    from meridian.config import RiskPolicy

    return RiskPolicy(
        max_position_weight=Decimal("0.25"), max_sector_weight=Decimal("1"),
        min_cash_weight=Decimal("0.10"), max_daily_turnover=Decimal("1"),
        max_single_order_nav_percent=Decimal("0.25"), max_number_positions=10,
    )


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Meridian Alpha — Gate 3B.4 Shadow Daily Run",
        "",
        f"Status: **{report['authorization']}**",
        f"Mode: `{report['mode']}`; candidates researched: {len(report['candidate_selection'])}",
        f"Certified signals: {report['certified_signal_count']}; abstains: {report['abstain_count']}; blocked/non-executable: {report['blocked_non_executable_count']}",
        "",
        "| Ticker | Quant-only | Research status | Direction | Conviction | Grounded modifier |",
        "| --- | ---: | --- | --- | ---: | ---: |",
    ]
    for item in report["diagnostics"]:
        lines.append(
            f"| {item['ticker']} | {item['quant_only_score']} | {item['research_status']} | "
            f"{item['research_direction'] or '—'} | {item['research_conviction'] or 'UNKNOWN'} | {item['grounded_research_modifier']} |"
        )
    lines.extend(
        [
            "",
            "All evidence and graph outputs are synthetic/replay fixtures. No CertifiedAgentSignal was issued; no output is authorized for entry, allocation or execution.",
        ]
    )
    return "\n".join(lines) + "\n"


