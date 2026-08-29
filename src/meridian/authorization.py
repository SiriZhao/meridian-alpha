"""Fail-closed authorization from grounded research to executable alpha."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from meridian.config import EvidenceCompletenessPolicy
from meridian.evidence import EvidenceCompletenessDiagnostics, EvidenceCompletenessEvaluator
from meridian.research import (
    _CERTIFICATION_TOKEN,
    CertifiedAgentSignal,
    EvidenceCitationValidator,
    GroundedResearchSignal,
    GroundedResearchStatus,
    ResearchEvidencePacket,
)
from meridian.schemas import EvidencePointInTimeStatus

_EXECUTABLE_PIT = {
    EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF,
    EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
}

class EvidenceAuthorizationService:
    """Issue CertifiedAgentSignal only after every executable evidence gate."""

    def authorize(
        self,
        grounded: GroundedResearchSignal,
        packet: ResearchEvidencePacket,
        *,
        provider_capabilities: Any,
        completeness_policy: EvidenceCompletenessPolicy | None = None,
    ) -> CertifiedAgentSignal:
        if grounded.status is not GroundedResearchStatus.AVAILABLE:
            raise ValueError("grounded research is not available")
        if packet.ticker != grounded.ticker or packet.as_of != grounded.as_of:
            raise ValueError("grounded evidence identity mismatch")
        self._validate_capabilities(provider_capabilities)
        if packet.point_in_time_status not in _EXECUTABLE_PIT:
            raise ValueError("packet point-in-time status is not executable")
        if (
            packet.point_in_time_status is EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF
            and provider_capabilities.supports_live is not True
        ):
            raise ValueError("provider does not certify live point-in-time evidence")
        if (
            packet.point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
            and provider_capabilities.supports_historical is not True
        ):
            raise ValueError("provider does not certify historical point-in-time evidence")
        evidence = EvidenceCitationValidator().validate(
            packet,
            grounded.cited_evidence_ids,
            grounded.as_of,
            allow_synthetic=False,
        )
        if not evidence:
            raise ValueError("executable research requires evidence")
        for item in evidence:
            if item.point_in_time_status not in _EXECUTABLE_PIT:
                raise ValueError("evidence point-in-time status is not executable")
            if (
                item.point_in_time_status is EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF
                and provider_capabilities.supports_live is not True
            ):
                raise ValueError("provider capability conflicts with live evidence status")
            if (
                item.point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
                and provider_capabilities.supports_historical is not True
            ):
                raise ValueError("provider capability conflicts with historical evidence status")
            if "available_at" not in item.model_fields_set:
                raise ValueError("evidence available_at must be authoritative and explicit")
            if item.available_at is None or item.available_at > grounded.as_of:
                raise ValueError("evidence available_at is not executable")
            if not item.provider:
                raise ValueError("evidence provider provenance is required")
            if item.provider != provider_capabilities.provider_name:
                raise ValueError("evidence provider does not match authorized provider")
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
            raise ValueError("evidence completeness authorization failed: " + ",".join(diagnostics.violations))
        signal = grounded.to_agent_signal(packet, allow_synthetic=False)
        digest = hashlib.sha256(
            f"{packet.packet_id}|{signal.stable_json()}|{provider_capabilities.provider_name}".encode()
        ).hexdigest()[:24]
        return CertifiedAgentSignal(
            _authorization_token=_CERTIFICATION_TOKEN,
            signal=signal,
            packet_id=packet.packet_id,
            certificate_id=f"cert_{digest}",
            provider_name=provider_capabilities.provider_name,
            evidence_ids=tuple(item.stable_id for item in evidence),
        )

    @staticmethod
    def _validate_capabilities(capabilities: Any) -> None:
        for name in ("provider_name", "research_grade", "supports_point_in_time", "supports_historical", "supports_live"):
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

