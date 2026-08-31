"""Explicit application profiles and top-level report safety labels."""

from __future__ import annotations

from enum import StrEnum

from meridian.manual_authority import ManualReadinessCertificate, ManualReadinessStatus
from meridian.schemas import DailyDecision, RunStatus, StableModel


class RuntimeProfile(StrEnum):
    TEST = "TEST"
    REPLAY = "REPLAY"
    SHADOW_LIVE = "SHADOW_LIVE"
    MANUAL_DECISION_SUPPORT = "MANUAL_DECISION_SUPPORT"


class ReportStatus(StrEnum):
    BLOCKED = "BLOCKED"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    SHADOW = "SHADOW"
    READY_FOR_MANUAL_ENTRY = "READY_FOR_MANUAL_ENTRY"


def parse_profile(value: str) -> RuntimeProfile:
    """Parse only safe profiles; AUTO_EXECUTION is intentionally absent."""
    try:
        return RuntimeProfile(value.upper())
    except ValueError as error:
        raise ValueError("PROFILE_UNSUPPORTED_OR_AUTO_EXECUTION_FORBIDDEN") from error


def report_status_for(profile: RuntimeProfile, decision: DailyDecision | None = None, readiness_certificate: object | None = None) -> ReportStatus:
    if profile is RuntimeProfile.MANUAL_DECISION_SUPPORT:
        if (
            isinstance(readiness_certificate, ManualReadinessCertificate)
            and readiness_certificate.status is ManualReadinessStatus.READY
            and all(readiness_certificate.gates.values())
            and decision is not None
            and decision.overall_status is RunStatus.READY_FOR_MANUAL_ENTRY
            and not decision.blocked_reasons
        ):
            return ReportStatus.READY_FOR_MANUAL_ENTRY
        return ReportStatus.BLOCKED
    if profile is RuntimeProfile.SHADOW_LIVE:
        return ReportStatus.SHADOW
    if decision is not None and decision.overall_status in {
        RunStatus.BLOCKED_STALE_ACCOUNT,
        RunStatus.BLOCKED_STALE_MARKET,
        RunStatus.FAILED,
    }:
        return ReportStatus.BLOCKED
    return ReportStatus.ANALYSIS_ONLY


class DailyApplicationEnvelope(StableModel):
    """Sanitized result wrapper shared by CLI/MCP/reporting integrations."""

    profile: RuntimeProfile
    status: ReportStatus
    run_id: str
    authorization: str = "SHADOW / NOT AUTHORIZED FOR ENTRY"
    blockers: tuple[str, ...] = ()

