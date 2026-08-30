"""Project-owned research contracts and optional TradingAgents boundary."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from meridian.schemas import AgentSignal, EvidenceItem, EvidencePointInTimeStatus, StableModel


class ResearchStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_GROUNDING = "INSUFFICIENT_GROUNDING"
    GRAPH_SUMMARY_ONLY = "GRAPH_SUMMARY_ONLY"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    REJECTED_EVIDENCE = "REJECTED_EVIDENCE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    HISTORICAL_LIVE_CALL_FORBIDDEN = "HISTORICAL_LIVE_CALL_FORBIDDEN"
    LIVE_RESEARCH_DISABLED = "LIVE_RESEARCH_DISABLED"
    REPLAY_FIXTURE_INVALID = "REPLAY_FIXTURE_INVALID"


class ResearchMode(StrEnum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"


class PointInTimeStatus(StrEnum):
    LIVE_RESEARCH_OK = "LIVE_RESEARCH_OK"
    HISTORICAL_REPLAY_UNSAFE = "HISTORICAL_REPLAY_UNSAFE"
    HISTORICAL_LIVE_CALL_FORBIDDEN = "HISTORICAL_LIVE_CALL_FORBIDDEN"


class GraphResearchSummary(StableModel):
    """Safe qualitative metadata returned by a completed TradingAgents graph."""

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    as_of: datetime
    requested_as_of: datetime | None = None
    status: ResearchStatus = ResearchStatus.INSUFFICIENT_GROUNDING
    graph_rating: str | None = None
    selected_analysts: tuple[str, ...] = ()
    reports_present: tuple[str, ...] = ()
    provider: str
    model: str
    framework_version: str
    started_at: datetime
    completed_at: datetime
    warnings: tuple[str, ...] = ()
    point_in_time_status: PointInTimeStatus
    token_usage: int | None = None
    estimated_cost: Decimal | None = None
    duration_seconds: Decimal | None = None
    source_mode: str = "LIVE"

    @model_validator(mode="after")
    def validate_summary(self):
        if self.requested_as_of is None:
            object.__setattr__(self, "requested_as_of", self.as_of)
        requested_as_of = self.requested_as_of
        if requested_as_of is None or requested_as_of.tzinfo is None or requested_as_of.utcoffset() is None:
            raise ValueError("graph summary requested_as_of must be timezone-aware")
        if self.status is ResearchStatus.AVAILABLE:
            raise ValueError("a graph summary cannot be an AVAILABLE AgentSignal")
        for name, value in (("as_of", self.as_of), ("started_at", self.started_at), ("completed_at", self.completed_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"graph summary {name} must be timezone-aware")
        if self.completed_at < self.started_at:
            raise ValueError("graph summary completed_at must not precede started_at")
        if self.graph_rating is not None and self.graph_rating not in {"Buy", "Overweight", "Hold", "Underweight", "Sell"}:
            raise ValueError("graph rating is invalid")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("graph duration must be non-negative")
        return self

_CERTIFICATION_TOKEN = object()
_CERTIFIED_VIEW_TOKEN = object()

class CertifiedAgentSignal(StableModel):
    """Sealed executable research authorization issued by the evidence gate."""

    signal: AgentSignal
    packet_id: str = Field(min_length=1, max_length=128)
    certificate_id: str = Field(min_length=1, max_length=128)
    provider_name: str = Field(min_length=1, max_length=128)
    evidence_ids: tuple[str, ...] = ()

    def __init__(self, **data: Any) -> None:
        token = data.pop("_authorization_token", None)
        if token is not _CERTIFICATION_TOKEN:
            raise ValueError("CertifiedAgentSignal may only be issued by the evidence authorization service")
        super().__init__(**data)

    @property
    def ticker(self) -> str:
        return self.signal.ticker

    @property
    def as_of(self):
        return self.signal.as_of

    @property
    def direction(self) -> str:
        return self.signal.direction

    @property
    def conviction(self):
        return self.signal.conviction

class ResearchOutcome(StableModel):
    ticker: str
    as_of: datetime
    status: ResearchStatus
    signal: AgentSignal | None = None
    certified_signal: CertifiedAgentSignal | None = None
    provider: str
    framework: str = "TradingAgents"
    framework_version: str
    model_provider: str
    model_name: str
    started_at: datetime
    completed_at: datetime
    mode: ResearchMode
    point_in_time_status: PointInTimeStatus
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    retry_count: int = 0
    token_usage: int | None = None
    estimated_cost: Decimal | None = None
    graph_rating: str | None = None
    selected_analysts: tuple[str, ...] = ()
    reports_present: tuple[str, ...] = ()
    graph_summary: GraphResearchSummary | None = None
    duration_seconds: Decimal | None = None

    @model_validator(mode="after")
    def validate_result_identity(self):
        for name, value in (("as_of", self.as_of), ("started_at", self.started_at), ("completed_at", self.completed_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"research {name} must be timezone-aware")
        if self.signal is not None and (
            self.signal.ticker != self.ticker or self.signal.as_of != self.as_of
        ):
            raise ValueError("research signal identity does not match outcome")
        if self.certified_signal is not None and (
            self.certified_signal.ticker != self.ticker
            or self.certified_signal.as_of != self.as_of
        ):
            raise ValueError("certified signal identity does not match outcome")
        if self.status is ResearchStatus.AVAILABLE and self.signal is None:
            raise ValueError("AVAILABLE research outcome requires a signal")
        if self.status is not ResearchStatus.AVAILABLE and self.signal is not None:
            raise ValueError("failed research outcome must not contain a signal")
        if self.status is not ResearchStatus.AVAILABLE and self.certified_signal is not None:
            raise ValueError("failed research outcome must not contain a signal")
        if self.graph_summary is not None and (
            self.graph_summary.ticker != self.ticker
            or self.graph_summary.as_of != self.as_of
        ):
            raise ValueError("graph summary identity does not match outcome")
        if self.graph_summary is not None and self.status is ResearchStatus.AVAILABLE:
            raise ValueError("graph summary cannot be combined with an AVAILABLE outcome")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("research duration must be non-negative")
        if self.graph_rating is not None and self.graph_rating not in {
            "Buy",
            "Overweight",
            "Hold",
            "Underweight",
            "Sell",
        }:
            raise ValueError("graph rating is invalid")
        return self

    @property
    def available(self) -> bool:
        return self.status is ResearchStatus.AVAILABLE and self.certified_signal is not None


class ResearchEvidencePacket(StableModel):
    """Bounded Meridian-owned evidence input for future grounded normalization."""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    packet_id: str = Field(min_length=1, max_length=128)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    as_of: datetime
    created_at: datetime | None = None
    items: tuple[EvidenceItem, ...] = Field(default=(), max_length=500)
    provider_statuses: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    point_in_time_status: EvidencePointInTimeStatus = EvidencePointInTimeStatus.UNKNOWN
    empty_reason: str | None = None
    schema_version: str = "1"

    @model_validator(mode="after")
    def validate_packet(self):
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("evidence packet as_of must be timezone-aware")
        if self.created_at is None:
            object.__setattr__(self, "created_at", self.as_of)
        elif self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("evidence packet created_at must be timezone-aware")
        if not self.items and not self.empty_reason:
            raise ValueError("empty evidence packet requires an explicit reason")
        resolved_items = tuple(
            item
            if item.evidence_id is not None
            else item.model_copy(update={"evidence_id": item.stable_id})
            for item in self.items
        )
        object.__setattr__(self, "items", resolved_items)
        ids = [item.stable_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("evidence packet contains duplicate evidence IDs")
        for item in self.items:
            if item.available_at is None or item.available_at > self.as_of:
                raise ValueError("evidence available_at must not be after packet as_of")
            if item.observed_at > self.as_of:
                raise ValueError("evidence observed_at must not be after packet as_of")
            if not item.source.strip() or not item.evidence_type.strip():
                raise ValueError("evidence requires provenance")
        return self

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset(item.stable_id for item in self.items)

    def validate_citations(self, cited_evidence_ids: tuple[str, ...]) -> None:
        unknown = set(cited_evidence_ids) - self.evidence_ids
        if unknown:
            raise ValueError(f"unknown cited evidence id(s): {sorted(unknown)}")


class ResearchContextPacket(StableModel):
    """Mixed-trust research context for diagnostics and shadow reporting."""

    context_id: str = Field(min_length=1, max_length=128)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    as_of: datetime
    items: tuple[EvidenceItem, ...] = Field(default=(), max_length=500)
    created_at: datetime

    @model_validator(mode="after")
    def validate_context(self):
        for name, value in (("as_of", self.as_of), ("created_at", self.created_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"research context {name} must be timezone-aware")
        return self


class CertifiedEvidenceView(StableModel):
    """Sealed exact evidence input permitted for executable grounding.

    It is derived item-by-item from mixed context. The source context is never
    supplied to the executable normalizer, so unverified material cannot affect
    a model before citation validation.
    """

    packet: ResearchEvidencePacket
    context_id: str = Field(min_length=1, max_length=128)
    excluded: tuple[str, ...] = ()

    def __init__(self, **data: Any) -> None:
        token = data.pop("_certified_view_token", None)
        if token is not _CERTIFIED_VIEW_TOKEN:
            raise ValueError("CertifiedEvidenceView may only be built from a ResearchContextPacket")
        super().__init__(**data)

    @classmethod
    def from_context(
        cls,
        context: ResearchContextPacket,
        *,
        provider_registry: Mapping[str, Any],
        clock: Callable[[], datetime] | None = None,
    ) -> CertifiedEvidenceView:
        from meridian.evidence import EvidencePacketBuilder

        now = (clock or (lambda: datetime.now(UTC)))()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("certified evidence clock must be timezone-aware")
        accepted: list[EvidenceItem] = []
        excluded: list[str] = []
        executable_statuses = {
            EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF,
            EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
        }
        for item in context.items:
            reason: str | None = None
            provider = (item.provider or "").strip()
            capability = provider_registry.get(provider)
            if item.ticker is not None and item.ticker != context.ticker:
                reason = "IDENTITY_MISMATCH"
            elif "available_at" not in item.model_fields_set or item.available_at is None:
                reason = "AVAILABLE_AT_REQUIRED"
            elif item.available_at > context.as_of or item.observed_at > context.as_of:
                reason = "AFTER_DECISION_AS_OF"
            elif item.point_in_time_status not in executable_statuses:
                reason = "PIT_NOT_EXECUTABLE"
            elif capability is None:
                reason = "PROVIDER_CAPABILITY_UNAVAILABLE"
            elif str(getattr(capability, "provider_name", "")).strip() != provider:
                reason = "PROVIDER_CAPABILITY_MISMATCH"
            elif getattr(capability, "research_grade", False) is not True:
                reason = "PROVIDER_NOT_RESEARCH_GRADE"
            elif getattr(capability, "supports_point_in_time", False) is not True:
                reason = "PROVIDER_NOT_PIT_CAPABLE"
            elif item.point_in_time_status is EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF and getattr(capability, "supports_live", False) is not True:
                reason = "PROVIDER_NOT_LIVE_CAPABLE"
            elif item.point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT and getattr(capability, "supports_historical", False) is not True:
                reason = "PROVIDER_NOT_HISTORICAL_CAPABLE"
            if reason is None:
                accepted.append(item)
            else:
                excluded.append(f"{item.stable_id}:{reason}")
        status = EvidencePacketBuilder.aggregate_point_in_time_status(tuple(accepted))
        ids = ":".join(item.stable_id for item in accepted)
        digest = hashlib.sha256(f"{context.context_id}|{ids}".encode()).hexdigest()[:24]
        packet = ResearchEvidencePacket(
            packet_id=f"certified_{digest}", ticker=context.ticker, as_of=context.as_of,
            created_at=now, items=tuple(accepted), point_in_time_status=status,
            empty_reason="NO_CERTIFIED_EVIDENCE" if not accepted else None,
            warnings=tuple(excluded),
        )
        return cls(_certified_view_token=_CERTIFIED_VIEW_TOKEN, packet=packet,
                   context_id=context.context_id, excluded=tuple(excluded))

class GroundedResearchResult(StableModel):
    """Future normalization result; not used to manufacture a live signal yet."""

    direction: str = Field(pattern=r"^(BULLISH|BEARISH|NEUTRAL)$")
    research_conviction: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    thesis: str = Field(min_length=1, max_length=10000)
    risks: tuple[str, ...] = ()
    cited_evidence_ids: tuple[str, ...] = ()

    def validate_against(self, packet: ResearchEvidencePacket) -> GroundedResearchResult:
        packet.validate_citations(self.cited_evidence_ids)
        return self


class GroundedResearchStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    GRAPH_SUMMARY_ONLY = "GRAPH_SUMMARY_ONLY"
    INSUFFICIENT_GROUNDING = "INSUFFICIENT_GROUNDING"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    UNAVAILABLE = "UNAVAILABLE"
    LIVE_RESEARCH_DISABLED = "LIVE_RESEARCH_DISABLED"
    HISTORICAL_LIVE_CALL_FORBIDDEN = "HISTORICAL_LIVE_CALL_FORBIDDEN"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"


class GroundedResearchRequest(StableModel):
    """Bounded input crossing from graph research into grounding."""

    graph_summary: GraphResearchSummary
    evidence_packet: ResearchEvidencePacket
    as_of: datetime
    schema_version: str = "1"

    @model_validator(mode="after")
    def validate_identity(self):
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("grounded request as_of must be timezone-aware")
        if self.graph_summary.ticker != self.evidence_packet.ticker:
            raise ValueError("graph summary and evidence packet ticker mismatch")
        if self.graph_summary.as_of != self.evidence_packet.as_of:
            raise ValueError("graph summary and evidence packet as_of mismatch")
        if self.as_of != self.graph_summary.as_of:
            raise ValueError("grounded request as_of mismatch")
        if self.graph_summary.status is ResearchStatus.AVAILABLE:
            raise ValueError("graph summary cannot be an AVAILABLE signal")
        return self


class EvidenceCitationValidator:
    """Validate Meridian-owned evidence citations before signal creation."""

    def validate(
        self,
        packet: ResearchEvidencePacket,
        cited_evidence_ids: tuple[str, ...],
        as_of: datetime,
        *,
        require_citations: bool = True,
        allow_synthetic: bool = False,
    ) -> tuple[EvidenceItem, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("citation as_of must be timezone-aware")
        if packet.as_of != as_of:
            raise ValueError("citation as_of does not match packet as_of")
        if require_citations and not cited_evidence_ids:
            raise ValueError("at least one evidence citation is required")
        by_id = {item.stable_id: item for item in packet.items}
        if len(set(cited_evidence_ids)) != len(cited_evidence_ids):
            raise ValueError("duplicate evidence citation")
        resolved: list[EvidenceItem] = []
        for evidence_id in cited_evidence_ids:
            item = by_id.get(evidence_id)
            if item is None:
                raise ValueError(f"unknown cited evidence id: {evidence_id}")
            if item.ticker is not None and item.ticker != packet.ticker:
                raise ValueError("cited evidence belongs to a different ticker")
            if not item.source.strip():
                raise ValueError("cited evidence requires provenance source")
            if "available_at" not in item.model_fields_set:
                raise ValueError("cited evidence requires explicit available_at")
            if item.available_at is None or item.available_at > as_of:
                raise ValueError("cited evidence is after as_of")
            if item.observed_at > as_of:
                raise ValueError("cited evidence observation is after as_of")
            executable_statuses = {
                EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF,
                EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
                EvidencePointInTimeStatus.VERIFIED,
                EvidencePointInTimeStatus.RECENT,
            }
            if item.point_in_time_status not in executable_statuses and not allow_synthetic:
                raise ValueError("cited evidence is not executable-path point-in-time safe")
            resolved.append(item)
        return tuple(resolved)


class GroundedResearchSignal(StableModel):
    """Explicitly normalized research; graph ratings never create conviction."""

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    as_of: datetime
    direction: str = Field(pattern=r"^(BULLISH|BEARISH|NEUTRAL)$")
    conviction: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    thesis: str = Field(min_length=1, max_length=10000)
    risks: tuple[str, ...] = ()
    cited_evidence_ids: tuple[str, ...] = ()
    graph_rating: str | None = None
    status: GroundedResearchStatus = GroundedResearchStatus.AVAILABLE
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_signal(self):
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("grounded signal as_of must be timezone-aware")
        if self.graph_rating is not None and self.graph_rating not in {
            "Buy",
            "Overweight",
            "Hold",
            "Underweight",
            "Sell",
        }:
            raise ValueError("graph rating is invalid")
        if self.status is GroundedResearchStatus.AVAILABLE and not self.cited_evidence_ids:
            raise ValueError("AVAILABLE grounded signal requires evidence citations")
        if self.status is not GroundedResearchStatus.AVAILABLE and self.cited_evidence_ids:
            raise ValueError("non-available grounded signal must not cite executable evidence")
        return self

    def to_agent_signal(
        self,
        packet: ResearchEvidencePacket,
        *,
        allow_synthetic: bool = False,
    ) -> AgentSignal:
        if self.status is not GroundedResearchStatus.AVAILABLE:
            raise ValueError(f"grounded research is not available: {self.status.value}")
        if packet.ticker != self.ticker or packet.as_of != self.as_of:
            raise ValueError("grounded signal identity does not match evidence packet")
        evidence = EvidenceCitationValidator().validate(
            packet,
            self.cited_evidence_ids,
            self.as_of,
            allow_synthetic=allow_synthetic,
        )
        return AgentSignal(
            ticker=self.ticker,
            as_of=self.as_of,
            direction=self.direction,
            conviction=self.conviction,
            thesis=self.thesis,
            risks=self.risks,
            evidence=evidence,
            source="grounded-research",
        )


class GroundedResearchOutcome(StableModel):
    ticker: str
    as_of: datetime
    status: GroundedResearchStatus
    signal: GroundedResearchSignal | None = None
    provider: str
    model: str
    created_at: datetime
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    content_hash: str | None = None
    schema_version: str = "1"

    @model_validator(mode="after")
    def validate_outcome(self):
        for name, value in (("as_of", self.as_of), ("created_at", self.created_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"grounded outcome {name} must be timezone-aware")
        if self.signal is not None and (
            self.signal.ticker != self.ticker or self.signal.as_of != self.as_of
        ):
            raise ValueError("grounded signal identity does not match outcome")
        if self.signal is not None and self.signal.status is not self.status:
            raise ValueError("grounded signal status does not match outcome")
        if self.status is GroundedResearchStatus.AVAILABLE and self.signal is None:
            raise ValueError("AVAILABLE grounded outcome requires a signal")
        if self.status is not GroundedResearchStatus.AVAILABLE and self.signal is not None:
            raise ValueError("failed grounded outcome must not contain a signal")
        return self

    @property
    def available(self) -> bool:
        return self.status is GroundedResearchStatus.AVAILABLE and self.signal is not None


class GroundedResearchNormalizer(Protocol):
    def normalize(
        self,
        graph_summary: GraphResearchSummary,
        evidence_packet: ResearchEvidencePacket,
        as_of: datetime,
    ) -> GroundedResearchOutcome: ...


def _grounded_outcome(
    *,
    ticker: str,
    as_of: datetime,
    status: GroundedResearchStatus,
    provider: str,
    model: str,
    warnings: tuple[str, ...] = (),
    error_code: str | None = None,
    signal: GroundedResearchSignal | None = None,
) -> GroundedResearchOutcome:
    return GroundedResearchOutcome(
        ticker=ticker,
        as_of=as_of,
        status=status,
        signal=signal,
        provider=provider,
        model=model,
        created_at=datetime.now(UTC),
        warnings=warnings,
        error_code=error_code,
    )


class FakeGroundedResearchNormalizer:
    """Offline normalizer requiring explicit, preconfigured conviction."""

    provider = "synthetic-grounded"
    model = "explicit-fixture-v1"

    def __init__(
        self,
        signals: Mapping[str, GroundedResearchSignal | Mapping[str, object]] | None = None,
        *,
        allow_synthetic: bool = True,
    ) -> None:
        self.signals = dict(signals or {})
        self.allow_synthetic = allow_synthetic

    def normalize(
        self,
        graph_summary: GraphResearchSummary,
        evidence_packet: ResearchEvidencePacket,
        as_of: datetime,
    ) -> GroundedResearchOutcome:
        try:
            request = GroundedResearchRequest(
                graph_summary=graph_summary,
                evidence_packet=evidence_packet,
                as_of=as_of,
            )
            configured = self.signals.get(request.graph_summary.ticker)
            if configured is None:
                return _grounded_outcome(
                    ticker=request.graph_summary.ticker,
                    as_of=as_of,
                    status=GroundedResearchStatus.INSUFFICIENT_GROUNDING,
                    provider=self.provider,
                    model=self.model,
                    warnings=("NO_EXPLICIT_GROUNDED_FIXTURE",),
                    error_code="INSUFFICIENT_GROUNDING",
                )
            signal = (
                configured
                if isinstance(configured, GroundedResearchSignal)
                else GroundedResearchSignal.model_validate(configured)
            )
            EvidenceCitationValidator().validate(
                evidence_packet,
                signal.cited_evidence_ids,
                as_of,
                allow_synthetic=self.allow_synthetic,
            )
            if signal.ticker != request.graph_summary.ticker or signal.as_of != as_of:
                raise ValueError("grounded signal identity mismatch")
            return _grounded_outcome(
                ticker=signal.ticker,
                as_of=as_of,
                status=signal.status,
                provider=self.provider,
                model=self.model,
                warnings=signal.warnings,
                signal=signal if signal.status is GroundedResearchStatus.AVAILABLE else None,
            )
        except ValueError as error:
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.INVALID_OUTPUT,
                provider=self.provider,
                model=self.model,
                warnings=(str(error),),
                error_code="INVALID_OUTPUT",
            )


class LiveResearchShadowOptIn(StableModel):
    """Explicit ephemeral authority for a bounded LIVE research shadow run."""

    enabled: bool = False
    mode: str = Field(default="LIVE_SHADOW", pattern=r"^LIVE_SHADOW$")
    max_tickers: int = Field(default=2, ge=1, le=3)


def enable_live_research_shadow(settings: Any, opt_in: LiveResearchShadowOptIn) -> Any:
    """Return a runtime-only settings copy; checked-in defaults remain OFF."""
    if opt_in.enabled is not True:
        raise ValueError("LIVE_RESEARCH_SHADOW_OPT_IN_REQUIRED")
    return settings.model_copy(update={"live_enabled": True})


def normalize_certified_shadow(
    normalizer: GroundedResearchNormalizer,
    graph_summary: GraphResearchSummary,
    evidence_view: CertifiedEvidenceView,
    as_of: datetime,
) -> GroundedResearchOutcome:
    """Only this boundary may hand executable grounding input to a live model."""
    if not isinstance(evidence_view, CertifiedEvidenceView):
        raise TypeError("live shadow grounding requires CertifiedEvidenceView")
    return normalizer.normalize(graph_summary, evidence_view.packet, as_of)

class _DeepSeekGroundedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(AVAILABLE|ABSTAIN)$")
    reason: str = Field(min_length=1, max_length=2000)
    direction: str | None = None
    conviction: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    thesis: str | None = None
    risks: tuple[str, ...] = ()
    cited_evidence_ids: tuple[str, ...] = ()


class DeepSeekGroundedResearchNormalizer:
    """Code-only DeepSeek adapter; disabled by default and never used in TEST."""

    provider = "deepseek"

    def __init__(
        self,
        settings: Any,
        *,
        client_factory: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.model = settings.deep_model or settings.model

    def normalize(
        self,
        graph_summary: GraphResearchSummary,
        evidence_packet: ResearchEvidencePacket,
        as_of: datetime,
    ) -> GroundedResearchOutcome:
        if not self.settings.live_enabled:
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.LIVE_RESEARCH_DISABLED,
                provider=self.provider,
                model=self.model,
                warnings=("DeepSeek grounded normalizer is disabled by policy.",),
                error_code="LIVE_RESEARCH_DISABLED",
            )
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        try:
            request = GroundedResearchRequest(
                graph_summary=graph_summary, evidence_packet=evidence_packet, as_of=as_of
            )
        except ValueError as error:
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.INVALID_OUTPUT,
                provider=self.provider,
                model=self.model,
                warnings=(str(error),),
                error_code="INVALID_OUTPUT",
            )
        graph_summary = request.graph_summary
        evidence_packet = request.evidence_packet
        age = (self.clock() - as_of).total_seconds()
        if age < 0 or age > self.settings.live_as_of_tolerance_seconds:
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.HISTORICAL_LIVE_CALL_FORBIDDEN,
                provider=self.provider,
                model=self.model,
                warnings=("Historical live grounding is forbidden.",),
                error_code="HISTORICAL_LIVE_CALL_FORBIDDEN",
            )
        if not os.getenv("DEEPSEEK_API_KEY"):
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.UNAVAILABLE,
                provider=self.provider,
                model=self.model,
                warnings=("DEEPSEEK_API_KEY is missing.",),
                error_code="DEEPSEEK_API_KEY_MISSING",
            )
        try:
            factory = self.client_factory
            if factory is None:
                factory = importlib.import_module(
                    "tradingagents.llm_clients"
                ).create_llm_client
            client = factory(
                provider="deepseek",
                model=self.model,
                base_url=self.settings.endpoint or "https://api.deepseek.com",
                timeout=self.settings.timeout_seconds,
                max_retries=self.settings.llm_retry_budget,
            )
            llm = client.get_llm()
            structured = llm.with_structured_output(_DeepSeekGroundedOutput)
            evidence = [
                {
                    "evidence_id": item.stable_id,
                    "source": item.source,
                    "provider": item.provider,
                    "available_at": item.available_at.isoformat() if item.available_at else None,
                    "evidence_type": item.evidence_type,
                    "title": item.title,
                    "summary": item.summary,
                }
                for item in evidence_packet.items
            ]
            prompt = json.dumps(
                {
                    "ticker": graph_summary.ticker,
                    "as_of": as_of.isoformat(),
                    "evidence_only": True,
                    "evidence": evidence,
                    "instructions": (
                        "Return status AVAILABLE or ABSTAIN plus reason. For AVAILABLE return only direction, conviction, thesis, risks, "
                        "cited_evidence_ids. Use only supplied evidence IDs. Do not invent URLs, "
                        "timestamps, evidence, sizing, prices, orders, or chain-of-thought. "
                        "Abstain by returning insufficient grounding when evidence is inadequate."
                    ),
                },
                sort_keys=True,
                default=str,
            )
            result = structured.invoke(prompt)
            payload = result.model_dump() if isinstance(result, BaseModel) else result
            if not isinstance(payload, Mapping):
                raise ValueError("DeepSeek structured result is not a mapping")
            parsed = _DeepSeekGroundedOutput.model_validate(payload)
            decision_status = parsed.status
            reason = parsed.reason.strip()
            if decision_status == "ABSTAIN":
                return _grounded_outcome(
                    ticker=graph_summary.ticker,
                    as_of=as_of,
                    status=GroundedResearchStatus.INSUFFICIENT_GROUNDING,
                    provider=self.provider,
                    model=self.model,
                    warnings=(reason or "DeepSeek abstained due to insufficient grounding.",),
                    error_code="INSUFFICIENT_GROUNDING",
                )
            if decision_status != "AVAILABLE":
                raise ValueError("structured grounding status must be AVAILABLE or ABSTAIN")
            allowed = {
                key: value
                for key, value in parsed.model_dump(exclude_none=True).items()
                if key in {"direction", "conviction", "thesis", "risks", "cited_evidence_ids"}
            }
            signal = GroundedResearchSignal.model_validate(
                {
                    **allowed,
                    "ticker": graph_summary.ticker,
                    "as_of": as_of,
                    "status": GroundedResearchStatus.AVAILABLE,
                }
            )
            EvidenceCitationValidator().validate(
                evidence_packet, signal.cited_evidence_ids, as_of
            )
            return _grounded_outcome(
                ticker=signal.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.AVAILABLE,
                provider=self.provider,
                model=self.model,
                signal=signal,
            )
        except TimeoutError as error:
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.TIMEOUT,
                provider=self.provider,
                model=self.model,
                warnings=(str(error),),
                error_code="TIMEOUT",
            )
        except ValueError as error:
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.INVALID_OUTPUT,
                provider=self.provider,
                model=self.model,
                warnings=(str(error),),
                error_code="INVALID_OUTPUT",
            )
        except Exception as error:  # noqa: BLE001 - provider boundary
            return _grounded_outcome(
                ticker=graph_summary.ticker,
                as_of=as_of,
                status=GroundedResearchStatus.PROVIDER_ERROR,
                provider=self.provider,
                model=self.model,
                warnings=(type(error).__name__,),
                error_code="PROVIDER_ERROR",
            )


class GroundedResearchReplayStore:
    """Record/replay graph, packet, and grounded-signal artifacts separately."""

    schema_version = "1"

    def __init__(self, directory: Path):
        self.directory = directory

    @staticmethod
    def _digest(artifact: StableModel) -> str:
        return hashlib.sha256(artifact.stable_json().encode()).hexdigest()

    def _record(self, kind: str, artifact: Any, created_at: datetime) -> Path:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("replay created_at must be timezone-aware")
        ticker = str(artifact.ticker)
        as_of = artifact.as_of
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{kind}-{ticker}-{as_of.strftime('%Y%m%dT%H%M%SZ')}.json"
        payload = {
            "schema_version": self.schema_version,
            "artifact_type": kind,
            "created_at": created_at.isoformat(),
            "as_of": as_of.isoformat(),
            "ticker": ticker,
            "provider": getattr(artifact, "provider", None),
            "model": getattr(artifact, "model", None),
            "content_hash": self._digest(artifact),
            "artifact": artifact.model_dump(mode="json"),
        }
        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return path

    def record_graph(self, summary: GraphResearchSummary) -> Path:
        return self._record("graph", summary, summary.completed_at)

    def record_packet(self, packet: ResearchEvidencePacket) -> Path:
        return self._record("evidence", packet, packet.created_at or packet.as_of)

    def record_signal(self, signal: GroundedResearchSignal) -> Path:
        return self._record("grounded", signal, datetime.now(UTC))

    def _load(
        self,
        kind: str,
        ticker: str,
        as_of: datetime,
        model: type[StableModel],
    ) -> StableModel:
        path = self.directory / f"{kind}-{ticker}-{as_of.strftime('%Y%m%dT%H%M%SZ')}.json"
        if not path.is_file():
            raise FileNotFoundError(path.name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != self.schema_version or payload.get("artifact_type") != kind:
            raise ValueError("unsupported replay schema version or artifact type")
        artifact = model.model_validate(payload.get("artifact"))
        artifact_values = artifact.model_dump()
        if artifact_values.get("ticker") != ticker or artifact_values.get("as_of") != as_of:
            raise ValueError("replay fixture identity mismatch")
        if payload.get("content_hash") != self._digest(artifact):
            raise ValueError("replay content hash mismatch")
        return artifact

    def load_graph(self, ticker: str, as_of: datetime) -> GraphResearchSummary:
        return self._load("graph", ticker, as_of, GraphResearchSummary)  # type: ignore[return-value]

    def load_packet(self, ticker: str, as_of: datetime) -> ResearchEvidencePacket:
        return self._load("evidence", ticker, as_of, ResearchEvidencePacket)  # type: ignore[return-value]

    def load_signal(self, ticker: str, as_of: datetime) -> GroundedResearchSignal:
        return self._load("grounded", ticker, as_of, GroundedResearchSignal)  # type: ignore[return-value]


class ResearchEngine(Protocol):
    def analyze(
        self, ticker: str, as_of: datetime, market_context: dict[str, object]
    ) -> AgentSignal | ResearchOutcome: ...


def normalize_signal(
    *, ticker: str, as_of: datetime, raw: dict[str, object], source: str
) -> AgentSignal:
    if "direction" not in raw:
        raise ValueError("research direction is required")
    direction = str(raw["direction"]).upper()
    direction = {"BUY": "BULLISH", "SELL": "BEARISH", "HOLD": "NEUTRAL"}.get(direction, direction)
    if direction not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        raise ValueError("research direction is invalid")
    if "conviction" not in raw:
        raise ValueError("research conviction is required")
    conviction = Decimal(str(raw["conviction"]))
    if not Decimal("0") <= conviction <= Decimal("1"):
        raise ValueError("research conviction must be normalized to 0..1")
    raw_evidence = raw.get("evidence", ())
    if not isinstance(raw_evidence, (list, tuple)):
        raise ValueError("research evidence must be a list")
    evidence_items = []
    for item in raw_evidence:
        if isinstance(item, EvidenceItem):
            evidence_items.append(item)
        elif isinstance(item, dict):
            evidence_items.append(EvidenceItem.model_validate(item))
        else:
            raise ValueError("research signal requires structured timestamped evidence")
    evidence = tuple(evidence_items)
    if not evidence:
        raise ValueError("research signal requires structured timestamped evidence")
    thesis = raw.get("thesis")
    if not isinstance(thesis, str) or not thesis.strip():
        raise ValueError("research thesis is required")
    return AgentSignal(
        ticker=ticker,
        as_of=as_of,
        direction=direction,
        conviction=conviction,
        fundamental_score=_bounded(raw.get("fundamental_score")),
        technical_score=_bounded(raw.get("technical_score")),
        sentiment_score=_bounded(raw.get("sentiment_score")),
        news_score=_bounded(raw.get("news_score")),
        risk_score=_unit(raw.get("risk_score")),
        thesis=thesis,
        risks=_strings(raw.get("risks", ())),
        evidence=evidence,
        source=source,
    )


def _bounded(value: object) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not Decimal("-1") <= result <= Decimal("1"):
        raise ValueError("research component score must be -1..1")
    return result


def _unit(value: object) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not Decimal("0") <= result <= Decimal("1"):
        raise ValueError("research risk score must be 0..1")
    return result


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("research list field must be a list")
    return tuple(str(item) for item in value)


class FakeResearchEngine:
    def __init__(self, signals: dict[str, AgentSignal]):
        self.signals = signals

    def analyze(
        self, ticker: str, as_of: datetime, market_context: dict[str, object]
    ) -> AgentSignal:
        signal = self.signals.get(ticker)
        if signal is None:
            raise LookupError(f"No fake research signal configured for {ticker}")
        if signal.as_of != as_of:
            raise ValueError("fake signal timestamp does not match analysis date")
        return signal
