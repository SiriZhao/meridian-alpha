"""Single safe application boundary for CLI, MCP, and operator workflows."""

from __future__ import annotations

from datetime import datetime

from meridian.config import Policies
from meridian.long_shadow import DailySystemHealth, derive_daily_health
from meridian.orchestrator import DailyAnalysisService, DailyOrchestrator
from meridian.profiles import (
    DailyApplicationEnvelope,
    ReportStatus,
    RuntimeProfile,
    report_status_for,
)
from meridian.schemas import AccountSnapshot, DailyDecision


class DailyApplicationResult:
    """Shared result object; no profile can expose an execution capability."""

    def __init__(
        self,
        *,
        profile: RuntimeProfile,
        decision: DailyDecision,
        health: DailySystemHealth,
        blockers: tuple[str, ...] = (),
    ) -> None:
        self.profile = profile
        self.decision = decision
        self.health = health
        self.status = report_status_for(profile, decision)
        self.blockers = blockers

    @property
    def envelope(self) -> DailyApplicationEnvelope:
        return DailyApplicationEnvelope(
            profile=self.profile,
            status=self.status,
            run_id=self.decision.run_id,
            blockers=self.blockers,
        )


def run_daily_application(
    account_snapshot: AccountSnapshot,
    run_date: datetime,
    *,
    profile: RuntimeProfile = RuntimeProfile.TEST,
    policies: Policies | None = None,
    orchestrator: DailyOrchestrator | None = None,
    quote_ready: bool = False,
) -> DailyApplicationResult:
    """Run the shared analysis path under an explicit non-execution profile."""
    if profile is RuntimeProfile.MANUAL_DECISION_SUPPORT and not quote_ready:
        blockers = ("QUOTE_READY requires a certified execution quote.",)
    else:
        blockers = ()
    decision = DailyAnalysisService(orchestrator, policies).run(account_snapshot, run_date)
    components = {
        "account": account_snapshot.freshness_state.value,
        "market": decision.market_data_status.value,
        "research": "AVAILABLE" if decision.target_portfolio is not None else "UNVERIFIED",
        "quote": "AVAILABLE" if quote_ready else "UNVERIFIED",
        "risk": "PASS" if not decision.blocked_reasons else "BLOCKED",
        "reconciliation": "PASS" if not decision.blocked_reasons else "UNVERIFIED",
    }
    health = derive_daily_health(components, manual_gates_pass=not blockers)
    return DailyApplicationResult(profile=profile, decision=decision, health=health, blockers=blockers)


def top_level_status(result: DailyApplicationResult) -> str:
    """Return the exact status that must lead every operator report."""
    return result.status.value if isinstance(result.status, ReportStatus) else str(result.status)

