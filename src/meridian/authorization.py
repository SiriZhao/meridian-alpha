"""Fail-closed authorization from grounded research to executable alpha."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from meridian.config import EvidenceCompletenessPolicy
from meridian.evidence import (
    EvidenceCompletenessDiagnostics,
    EvidenceCompletenessEvaluator,
    EvidencePacketBuilder,
)
from meridian.research import (
    _CERTIFICATION_TOKEN,
    CertifiedAgentSignal,
    EvidenceCitationValidator,
    GroundedResearchSignal,
    GroundedResearchStatus,
    ResearchEvidencePacket,
)
from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus

_EXECUTABLE_PIT = {
    EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF,
    EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
}


class EvidenceAuthorizationService:
    """Issue ``CertifiedAgentSignal`` only after every evidence gate passes.

    A packet may contain observations from several providers.  Authorization is
    therefore resolved per cited item through ``provider_registry``; a single
    provider certificate cannot authorize another provider's evidence.
    ``provider_capabilities`` remains a compatibility shorthand for callers
    that supply a genuinely single-provider packet.
    """

    def authorize(
        self,
        grounded: GroundedResearchSignal,
        packet: ResearchEvidencePacket,
        *,
        provider_capabilities: Any | None = None,
        provider_registry: Mapping[str, Any] | None = None,
        completeness_policy: EvidenceCompletenessPolicy | None = None,
    ) -> CertifiedAgentSignal:
        if grounded.status is not GroundedResearchStatus.AVAILABLE:
            raise ValueError("grounded research is not available")
        if packet.ticker != grounded.ticker or packet.as_of != grounded.as_of:
            raise ValueError("grounded evidence identity mismatch")
        registry = self._build_registry(provider_capabilities, provider_registry)
        if not registry:
            raise ValueError("PROVIDER_CAPABILITY_UNAVAILABLE")
        if packet.point_in_time_status not in _EXECUTABLE_PIT:
            raise ValueError("packet point-in-time status is not executable")
        # Recompute the packet status from item certifications so a caller
        # cannot manually overstate a mixed or weak packet as executable PIT.
        aggregated_status = EvidencePacketBuilder.aggregate_point_in_time_status(packet.items)
        if aggregated_status is not packet.point_in_time_status:
            raise ValueError("packet point-in-time status overstates item certification")
        evidence = EvidenceCitationValidator().validate(
            packet,
            grounded.cited_evidence_ids,
            grounded.as_of,
            allow_synthetic=False,
        )
        if not evidence:
            raise ValueError("executable research requires evidence")
        for item in evidence:
            provider_name = (item.provider or "").strip()
            capabilities = registry.get(provider_name)
            if capabilities is None:
                raise ValueError(f"PROVIDER_CAPABILITY_UNAVAILABLE:{provider_name or 'UNKNOWN'}")
            self._validate_capabilities(capabilities)
            if str(capabilities.provider_name) != provider_name:
                raise ValueError("provider capability certificate name mismatch")
            self._validate_item_capability(item, capabilities, grounded.as_of)
            if "available_at" not in item.model_fields_set:
                raise ValueError("evidence available_at must be authoritative and explicit")
            if item.available_at is None or item.available_at > grounded.as_of:
                raise ValueError("evidence available_at is not executable")
            if not item.provider:
                raise ValueError("evidence provider provenance is required")
        policy = completeness_policy or EvidenceCompletenessPolicy(
            minimum_total_items=1,
            minimum_distinct_sources=1,
            required_evidence_types=(),
            maximum_age_by_type={},
            minimum_point_in_time_quality=Decimal("1"),
        )
        diagnostics: EvidenceCompletenessDiagnostics = EvidenceCompletenessEvaluator(policy).evaluate(
            packet, grounded.as_of
        )
        if not diagnostics.complete:
            raise ValueError(
                "evidence completeness authorization failed: "
                + ",".join(diagnostics.violations)
            )
        signal = grounded.to_agent_signal(packet, allow_synthetic=False)
        provider_names = ",".join(sorted({item.provider or "UNKNOWN" for item in evidence}))
        digest = hashlib.sha256(
            f"{packet.packet_id}|{signal.stable_json()}|{provider_names}".encode()
        ).hexdigest()[:24]
        return CertifiedAgentSignal(
            _authorization_token=_CERTIFICATION_TOKEN,
            signal=signal,
            packet_id=packet.packet_id,
            certificate_id=f"cert_{digest}",
            provider_name=provider_names,
            evidence_ids=tuple(item.stable_id for item in evidence),
        )

    @staticmethod
    def _build_registry(
        provider_capabilities: Any | None,
        provider_registry: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if provider_registry is not None:
            if not isinstance(provider_registry, Mapping):
                raise ValueError("PROVIDER_CAPABILITY_UNAVAILABLE:registry-not-a-map")
            registry = {str(name): capability for name, capability in provider_registry.items()}
            if provider_capabilities is not None:
                name = str(getattr(provider_capabilities, "provider_name", "")).strip()
                if name and name not in registry:
                    registry[name] = provider_capabilities
            return registry
        if provider_capabilities is None:
            return {}
        name = str(getattr(provider_capabilities, "provider_name", "")).strip()
        return {name: provider_capabilities} if name else {}

    @staticmethod
    def _validate_item_capability(
        item: EvidenceItem,
        capabilities: Any,
        as_of: Any,
    ) -> None:
        _ = as_of
        if item.point_in_time_status not in _EXECUTABLE_PIT:
            raise ValueError("evidence point-in-time status is not executable")
        if capabilities.supports_point_in_time is not True:
            raise ValueError("provider does not support point-in-time evidence")
        if capabilities.research_grade is not True:
            raise ValueError("provider is not research-grade")
        if item.point_in_time_status is EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF:
            if capabilities.supports_live is not True:
                raise ValueError("provider capability conflicts with live evidence status")
        elif capabilities.supports_historical is not True:
            raise ValueError("provider capability conflicts with historical evidence status")

    @staticmethod
    def _validate_capabilities(capabilities: Any) -> None:
        for name in (
            "provider_name",
            "research_grade",
            "supports_point_in_time",
            "supports_historical",
            "supports_live",
        ):
            if not hasattr(capabilities, name):
                raise ValueError(f"provider capability missing: {name}")
        if not str(capabilities.provider_name).strip():
            raise ValueError("provider capability provider_name must not be blank")
        if capabilities.research_grade is not True:
            raise ValueError("provider is not research-grade")
        if capabilities.supports_point_in_time is not True:
            raise ValueError("provider does not support point-in-time evidence")
        if capabilities.supports_historical is not True and capabilities.supports_live is not True:
            raise ValueError("provider declares neither historical nor live support")
        for name in ("supports_live", "supports_historical", "supports_point_in_time"):
            if not isinstance(getattr(capabilities, name), bool):
                raise ValueError(f"provider capability {name} must be boolean")
