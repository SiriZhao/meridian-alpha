"""Offline-first bounded research pipeline.

This application boundary composes deterministic candidate selection, a
project-owned graph provider, Meridian evidence, and grounded normalization.
It never grants a research provider execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from meridian.authorization import EvidenceAuthorizationService
from meridian.candidates import CandidateSelector, ResearchCandidateSet
from meridian.config import EvidencePacketPolicy, ResearchBudgetPolicy
from meridian.evidence import EvidencePacketBuilder, EvidenceProvider
from meridian.research import (
    CertifiedAgentSignal,
    CertifiedEvidenceView,
    EvidenceCitationValidator,
    GraphResearchSummary,
    GroundedResearchNormalizer,
    GroundedResearchOutcome,
    GroundedResearchReplayStore,
    GroundedResearchStatus,
    PointInTimeStatus,
    ResearchContextPacket,
    ResearchEvidencePacket,
    ResearchMode,
    ResearchOutcome,
    ResearchStatus,
)
from meridian.schemas import StableModel


class ResearchPipelineMode(StrEnum):
    TEST = "TEST"
    REPLAY = "REPLAY"
    LIVE = "LIVE"


class ResearchPipelineStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_GROUNDING = "INSUFFICIENT_GROUNDING"
    UNAVAILABLE = "UNAVAILABLE"
    LIVE_RESEARCH_DISABLED = "LIVE_RESEARCH_DISABLED"
    HISTORICAL_REPLAY_UNSAFE = "HISTORICAL_REPLAY_UNSAFE"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    NO_CANDIDATES = "NO_CANDIDATES"


class GraphResearchProvider(Protocol):
    def analyze(
        self, ticker: str, as_of: datetime, market_context: dict[str, object]
    ) -> GraphResearchSummary | ResearchOutcome: ...


class ResearchPipelineResult(StableModel):
    as_of: datetime
    mode: ResearchPipelineMode
    status: ResearchPipelineStatus
    candidate_set: ResearchCandidateSet
    graph_summaries: tuple[GraphResearchSummary, ...] = ()
    evidence_packets: tuple[ResearchEvidencePacket, ...] = ()
    grounded_outcomes: tuple[GroundedResearchOutcome, ...] = ()
    agent_signals: tuple[CertifiedAgentSignal, ...] = ()
    warnings: tuple[str, ...] = ()
    synthetic: bool = False

    @property
    def certified_signals(self) -> tuple[CertifiedAgentSignal, ...]:
        return self.agent_signals

    @property
    def content_hash(self) -> str:
        import hashlib

        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class FakeGraphResearchProvider:
    """Deterministic graph-summary fixture; it never calls a network provider."""

    provider = "synthetic-tradingagents-graph"
    model = "synthetic-graph-v1"
    framework_version = "0.3.1"

    def __init__(self, summaries: Mapping[str, GraphResearchSummary] | None = None):
        self.summaries = dict(summaries or {})
        self.calls: list[str] = []

    def analyze(
        self, ticker: str, as_of: datetime, market_context: dict[str, object]
    ) -> GraphResearchSummary:
        _ = market_context
        self.calls.append(ticker)
        summary = self.summaries.get(ticker)
        if summary is not None:
            if summary.as_of != as_of:
                raise ValueError("synthetic graph fixture as_of mismatch")
            return summary
        return GraphResearchSummary(
            ticker=ticker,
            as_of=as_of,
            status=ResearchStatus.GRAPH_SUMMARY_ONLY,
            graph_rating="Hold",
            selected_analysts=("market", "social", "news", "fundamentals"),
            reports_present=(
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
            ),
            provider=self.provider,
            model=self.model,
            framework_version=self.framework_version,
            started_at=as_of,
            completed_at=as_of,
            warnings=("SYNTHETIC - NOT LIVE DATA",),
            point_in_time_status=PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE,
            duration_seconds=Decimal("0"),
            source_mode="TEST",
        )


class ResearchPipelineService:
    """Compose bounded graph research and grounded normalization."""

    def __init__(
        self,
        budget_policy: ResearchBudgetPolicy,
        *,
        candidate_selector: CandidateSelector | None = None,
        graph_provider: GraphResearchProvider | None = None,
        evidence_builder: EvidencePacketBuilder | None = None,
        evidence_providers: Sequence[EvidenceProvider] = (),
        normalizer: GroundedResearchNormalizer | None = None,
        replay_store: GroundedResearchReplayStore | None = None,
        live_enabled: bool = False,
    ) -> None:
        self.budget_policy = budget_policy
        self.candidate_selector = candidate_selector or CandidateSelector()
        self.graph_provider = graph_provider
        self.evidence_builder = evidence_builder or EvidencePacketBuilder(
            EvidencePacketPolicy(
                max_total_evidence_items=50,
                max_items_per_type=10,
                max_summary_characters_per_item=2000,
            )
        )
        self.evidence_providers = tuple(evidence_providers)
        self.normalizer = normalizer
        self.replay_store = replay_store
        self.live_enabled = live_enabled

    def run(
        self,
        tickers: Sequence[str],
        as_of: datetime,
        quant_features: Mapping[str, Mapping[str, object]],
        *,
        existing_holdings: Sequence[str] = (),
        mode: ResearchPipelineMode = ResearchPipelineMode.TEST,
        market_contexts: Mapping[str, dict[str, object]] | None = None,
    ) -> ResearchPipelineResult:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("research pipeline as_of must be timezone-aware")
        candidates = self.candidate_selector.build(
            tuple(tickers),
            quant_features,
            as_of,
            existing_holdings=tuple(existing_holdings),
            policy=self.budget_policy,
        )
        if mode is ResearchPipelineMode.LIVE and not self.live_enabled:
            return self._disabled_result(candidates, as_of)
        if mode in {ResearchPipelineMode.TEST, ResearchPipelineMode.REPLAY}:
            if (
                self._network_capable(self.graph_provider)
                or self._network_capable(self.normalizer)
                or any(self._network_capable(provider) for provider in self.evidence_providers)
            ):
                return ResearchPipelineResult(
                    as_of=as_of,
                    mode=mode,
                    status=ResearchPipelineStatus.UNAVAILABLE,
                    candidate_set=candidates,
                    warnings=("NETWORK_PROVIDER_FORBIDDEN_IN_OFFLINE_MODE",),
                    synthetic=mode is ResearchPipelineMode.TEST,
                )
        if not candidates.candidates:
            return ResearchPipelineResult(
                as_of=as_of,
                mode=mode,
                status=ResearchPipelineStatus.NO_CANDIDATES,
                candidate_set=candidates,
                warnings=("NO_RESEARCH_CANDIDATES",),
                synthetic=mode is ResearchPipelineMode.TEST,
            )

        summaries: list[GraphResearchSummary] = []
        packets: list[ResearchEvidencePacket] = []
        grounded: list[GroundedResearchOutcome] = []
        signals: list[CertifiedAgentSignal] = []
        warnings: list[str] = []
        for candidate in candidates.candidates:
            ticker = candidate.ticker
            context = (market_contexts or {}).get(ticker, {})
            if mode is ResearchPipelineMode.REPLAY:
                self._run_replay_one(
                    ticker,
                    as_of,
                    summaries,
                    packets,
                    grounded,
                    signals,
                    warnings,
                )
                continue
            summary, graph_outcome = self._run_graph_one(ticker, as_of, context)
            if summary is None:
                if graph_outcome is not None:
                    grounded.append(
                        GroundedResearchOutcome(
                            ticker=ticker,
                            as_of=as_of,
                            status=GroundedResearchStatus.UNAVAILABLE,
                            provider=graph_outcome.provider,
                            model=graph_outcome.model_name,
                            created_at=graph_outcome.completed_at,
                            warnings=graph_outcome.warnings,
                            error_code=graph_outcome.error_code or graph_outcome.status.value,
                        )
                    )
                else:
                    grounded.append(
                        GroundedResearchOutcome(
                            ticker=ticker,
                            as_of=as_of,
                            status=GroundedResearchStatus.UNAVAILABLE,
                            provider="UNCONFIGURED",
                            model="UNCONFIGURED",
                            created_at=datetime.now(UTC),
                            warnings=("GRAPH_PROVIDER_UNAVAILABLE",),
                            error_code="GRAPH_PROVIDER_UNAVAILABLE",
                        )
                    )
                continue
            summaries.append(summary)
            packet = self.evidence_builder.gather(
                ticker,
                as_of,
                self.evidence_providers,
            )
            packets.append(packet)
            normalizer_packet = packet
            provider_registry: dict[str, object] = {}
            if mode is ResearchPipelineMode.LIVE:
                for provider in self.evidence_providers:
                    name = provider.capabilities.provider_name
                    existing = provider_registry.get(name)
                    if existing is not None and existing != provider.capabilities:
                        raise ValueError(f"PROVIDER_CAPABILITY_CONFLICT:{name}")
                    provider_registry[name] = provider.capabilities
                context_packet = ResearchContextPacket(
                    context_id=f"context_{packet.packet_id}", ticker=ticker,
                    as_of=as_of, items=packet.items, created_at=packet.created_at or as_of,
                )
                certified_view = CertifiedEvidenceView.from_context(
                    context_packet, provider_registry=provider_registry,
                )
                normalizer_packet = certified_view.packet
            if self.normalizer is None:
                result = GroundedResearchOutcome(
                    ticker=ticker,
                    as_of=as_of,
                    status=GroundedResearchStatus.INSUFFICIENT_GROUNDING,
                    provider="UNCONFIGURED",
                    model="UNCONFIGURED",
                    created_at=datetime.now(UTC),
                    warnings=("GROUNDED_NORMALIZER_UNAVAILABLE",),
                    error_code="GROUNDED_NORMALIZER_UNAVAILABLE",
                )
            else:
                result = self.normalizer.normalize(summary, normalizer_packet, as_of)
            grounded.append(result)
            if result.available and result.signal is not None:
                # TEST and REPLAY are deliberately non-executable.  A
                # CertifiedAgentSignal can only be issued by the authorization
                # service for a live, independently certified evidence packet.
                if mode is not ResearchPipelineMode.LIVE:
                    warnings.append(f"{ticker}:NON_EXECUTABLE_MODE:{mode.value}")
                else:
                    try:
                        if not provider_registry:
                            raise ValueError("PROVIDER_CAPABILITY_UNAVAILABLE")
                        signals.append(
                            EvidenceAuthorizationService().authorize(
                                result.signal,
                                normalizer_packet,
                                provider_registry=provider_registry,
                            )
                        )
                    except ValueError as error:
                        warnings.append(f"{ticker}:AGENT_SIGNAL_REJECTED:{error}")
            else:
                warnings.extend(f"{ticker}:{warning}" for warning in result.warnings)

        status = self._status(mode, summaries, grounded, signals)
        return ResearchPipelineResult(
            as_of=as_of,
            mode=mode,
            status=status,
            candidate_set=candidates,
            graph_summaries=tuple(sorted(summaries, key=lambda item: item.ticker)),
            evidence_packets=tuple(sorted(packets, key=lambda item: item.ticker)),
            grounded_outcomes=tuple(sorted(grounded, key=lambda item: item.ticker)),
            agent_signals=tuple(sorted(signals, key=lambda item: item.ticker)),
            warnings=tuple(warnings),
            synthetic=mode is ResearchPipelineMode.TEST,
        )

    def _run_graph_one(
        self, ticker: str, as_of: datetime, context: dict[str, object]
    ) -> tuple[GraphResearchSummary | None, ResearchOutcome | None]:
        if self.graph_provider is None:
            return None, None
        try:
            result = self.graph_provider.analyze(ticker, as_of, context)
        except Exception as error:  # noqa: BLE001 - per-ticker fail-closed isolation
            return (
                None,
                ResearchOutcome(
                    ticker=ticker,
                    as_of=as_of,
                    status=ResearchStatus.PROVIDER_ERROR,
                    provider="graph-provider",
                    framework="GraphResearchProvider",
                    framework_version="UNKNOWN",
                    model_provider="UNKNOWN",
                    model_name="UNKNOWN",
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    mode=ResearchMode.LIVE,
                    point_in_time_status=PointInTimeStatus.HISTORICAL_LIVE_CALL_FORBIDDEN,
                    warnings=(type(error).__name__,),
                    error_code="GRAPH_PROVIDER_ERROR",
                ),
            )
        if isinstance(result, GraphResearchSummary):
            return result, None
        if isinstance(result, ResearchOutcome) and result.graph_summary is not None:
            return result.graph_summary, result
        return None, result if isinstance(result, ResearchOutcome) else None

    def _run_replay_one(
        self,
        ticker: str,
        as_of: datetime,
        summaries: list[GraphResearchSummary],
        packets: list[ResearchEvidencePacket],
        grounded: list[GroundedResearchOutcome],
        signals: list[CertifiedAgentSignal],
        warnings: list[str],
    ) -> None:
        if self.replay_store is None:
            grounded.append(
                GroundedResearchOutcome(
                    ticker=ticker,
                    as_of=as_of,
                    status=GroundedResearchStatus.UNAVAILABLE,
                    provider="REPLAY",
                    model="REPLAY",
                    created_at=datetime.now(UTC),
                    warnings=("REPLAY_STORE_UNAVAILABLE",),
                    error_code="REPLAY_STORE_UNAVAILABLE",
                )
            )
            return
        try:
            summary = self.replay_store.load_graph(ticker, as_of)
            packet = self.replay_store.load_packet(ticker, as_of)
            signal = self.replay_store.load_signal(ticker, as_of)
            EvidenceCitationValidator().validate(
                packet, signal.cited_evidence_ids, as_of, allow_synthetic=True
            )
            summaries.append(summary)
            packets.append(packet)
            outcome = GroundedResearchOutcome(
                ticker=ticker,
                as_of=as_of,
                status=signal.status,
                signal=signal if signal.status is GroundedResearchStatus.AVAILABLE else None,
                provider="REPLAY",
                model="REPLAY",
                created_at=datetime.now(UTC),
                warnings=signal.warnings,
            )
            grounded.append(outcome)
            if outcome.available and outcome.signal is not None:
                warnings.append(f"{ticker}:REPLAY_SIGNAL_NON_EXECUTABLE")
        except Exception as error:  # noqa: BLE001 - invalid fixtures fail closed
            warnings.append(f"{ticker}:REPLAY_FIXTURE_INVALID:{type(error).__name__}")
            grounded.append(
                GroundedResearchOutcome(
                    ticker=ticker,
                    as_of=as_of,
                    status=GroundedResearchStatus.INVALID_OUTPUT,
                    provider="REPLAY",
                    model="REPLAY",
                    created_at=datetime.now(UTC),
                    warnings=(type(error).__name__,),
                    error_code="REPLAY_FIXTURE_INVALID",
                )
            )

    @staticmethod
    def _status(
        mode: ResearchPipelineMode,
        summaries: Sequence[GraphResearchSummary],
        grounded: Sequence[GroundedResearchOutcome],
        signals: Sequence[CertifiedAgentSignal],
    ) -> ResearchPipelineStatus:
        if mode is ResearchPipelineMode.REPLAY and any(
            summary.point_in_time_status is PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE
            for summary in summaries
        ):
            return ResearchPipelineStatus.HISTORICAL_REPLAY_UNSAFE
        if signals and len(signals) == len(grounded):
            return ResearchPipelineStatus.AVAILABLE
        if signals:
            return ResearchPipelineStatus.PARTIAL
        if summaries:
            return ResearchPipelineStatus.INSUFFICIENT_GROUNDING
        return ResearchPipelineStatus.UNAVAILABLE

    @staticmethod
    def _network_capable(provider: object | None) -> bool:
        if provider is None:
            return False
        if bool(getattr(provider, "network_capable", False)):
            return True
        capabilities = getattr(provider, "capabilities", None)
        if bool(getattr(capabilities, "supports_live", False)):
            return True
        settings = getattr(provider, "settings", None)
        return bool(getattr(settings, "live_enabled", False))

    @staticmethod
    def _disabled_result(
        candidates: ResearchCandidateSet, as_of: datetime
    ) -> ResearchPipelineResult:
        return ResearchPipelineResult(
            as_of=as_of,
            mode=ResearchPipelineMode.LIVE,
            status=ResearchPipelineStatus.LIVE_RESEARCH_DISABLED,
            candidate_set=candidates,
            warnings=("LIVE_RESEARCH_DISABLED",),
        )
