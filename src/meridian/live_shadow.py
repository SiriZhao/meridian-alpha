"""LEGACY / DEPRECATED bounded DeepSeek grounding shadow runner.

This module has no account, broker, order, allocation, or execution dependency.
Its retained normalizer is permanently network-disabled and fails closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meridian.authorization import EvidenceAuthorizationService
from meridian.research import (
    CertifiedAgentSignal,
    CertifiedEvidenceView,
    DeepSeekGroundedResearchNormalizer,
    GraphResearchSummary,
    GroundedResearchOutcome,
    LiveResearchShadowOptIn,
    PointInTimeStatus,
    ResearchContextPacket,
    ResearchStatus,
    enable_live_research_shadow,
    normalize_certified_shadow,
)
from meridian.schemas import StableModel
from meridian.sec_filing_metadata import SECAccessionCertifiedFactsProvider


class LiveShadowGroundingRun(StableModel):
    as_of: datetime
    outcomes: tuple[GroundedResearchOutcome, ...]
    certified_signals: tuple[CertifiedAgentSignal, ...] = ()
    evidence_counts: dict[str, int]
    warnings: tuple[str, ...] = ()
    authorization: str = "SHADOW / NOT AUTHORIZED FOR ENTRY"


def run_live_certified_grounding_shadow(
    settings: Any,
    opt_in: LiveResearchShadowOptIn,
    *,
    tickers: tuple[str, ...] = ("AAPL", "NVDA"),
    now: datetime | None = None,
) -> LiveShadowGroundingRun:
    """Run at most three real certified-evidence grounding calls, shadow-only."""
    if len(tickers) > opt_in.max_tickers:
        raise ValueError("LIVE_RESEARCH_SHADOW_TICKER_BUDGET_EXCEEDED")
    as_of = now or datetime.now(UTC)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("live shadow as_of must be timezone-aware")
    runtime_settings = enable_live_research_shadow(settings, opt_in)
    provider = SECAccessionCertifiedFactsProvider()
    normalizer = DeepSeekGroundedResearchNormalizer(runtime_settings)
    outcomes: list[GroundedResearchOutcome] = []
    certified: list[CertifiedAgentSignal] = []
    counts: dict[str, int] = {}
    warnings: list[str] = []
    for ticker in tickers:
        items = provider.get_evidence(ticker, as_of)
        context = ResearchContextPacket(
            context_id=f"live-shadow-{ticker}-{as_of.strftime('%Y%m%dT%H%M%SZ')}",
            ticker=ticker,
            as_of=as_of,
            created_at=as_of,
            items=items,
        )
        view = CertifiedEvidenceView.from_context(
            context,
            provider_registry={provider.provider_name: provider.capabilities},
            clock=lambda: as_of,
        )
        counts[ticker] = len(view.packet.items)
        if not view.packet.items:
            warnings.append(f"{ticker}:NO_CERTIFIED_EVIDENCE")
            continue
        summary = GraphResearchSummary(
            ticker=ticker,
            as_of=as_of,
            status=ResearchStatus.GRAPH_SUMMARY_ONLY,
            provider="meridian-live-shadow",
            model="none",
            framework_version="1",
            started_at=as_of,
            completed_at=as_of,
            point_in_time_status=PointInTimeStatus.LIVE_RESEARCH_OK,
            source_mode="LIVE_SHADOW",
        )
        outcome = normalize_certified_shadow(normalizer, summary, view, as_of)
        outcomes.append(outcome)
        if outcome.available and outcome.signal is not None:
            try:
                certified.append(EvidenceAuthorizationService().authorize(
                    outcome.signal,
                    view.packet,
                    provider_registry={provider.provider_name: provider.capabilities},
                ))
            except ValueError as error:
                warnings.append(f"{ticker}:AUTHORIZATION_REJECTED:{error}")
        else:
            warnings.extend(f"{ticker}:{warning}" for warning in outcome.warnings)
    return LiveShadowGroundingRun(
        as_of=as_of,
        outcomes=tuple(outcomes),
        certified_signals=tuple(certified),
        evidence_counts=counts,
        warnings=tuple(warnings),
    )
