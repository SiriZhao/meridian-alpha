"""Safe daily closure from a sanitized Host snapshot to manual-only reports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from meridian.allocation import allocate_with_fallback
from meridian.config import Policies
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.orders import OrderPlanner, ProjectedPortfolioValidator
from meridian.reconciliation import ReconciliationEngine, ReconciliationResult
from meridian.risk import RiskEngine
from meridian.runtime import RuntimePaths
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    AlphaScore,
    DailyDecision,
    FreshnessState,
    MarketSnapshot,
    OrderDraft,
    RunStatus,
    TargetPortfolio,
)


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_snapshot(path: Path, *, now: datetime | None = None, replay: bool = False) -> AccountSnapshot:
    envelope = HostAccountSnapshotEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
    return normalize_host_snapshot(envelope, trusted_now=(now or datetime.now(UTC)) if replay else None, replay=replay)


def load_market_fixture(path: Path) -> dict[str, MarketSnapshot]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("quotes"), list):
        raise ValueError("MARKET_FIXTURE_INVALID")
    quotes = tuple(MarketSnapshot.model_validate(item) for item in raw["quotes"])
    if len({quote.ticker for quote in quotes}) != len(quotes):
        raise ValueError("MARKET_FIXTURE_DUPLICATE_SYMBOL")
    return {quote.ticker: quote for quote in quotes}


@dataclass(frozen=True)
class DailyClosureResult:
    decision: DailyDecision
    report: dict[str, object]
    report_json: Path | None = None
    report_markdown: Path | None = None


class DailyClosureService:
    """The only Stage-C closure service; it never enables broker submission."""

    def __init__(self, policies: Policies) -> None:
        self.policies = policies

    def run(self, account: AccountSnapshot, quotes: dict[str, MarketSnapshot], *, cutoff: datetime) -> DailyClosureResult:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("DAILY_CUTOFF_TIMEZONE_REQUIRED")
        market_hash = _hash({ticker: quote.model_dump(mode="json") for ticker, quote in sorted(quotes.items())})
        policy_hash = _hash(self.policies.models.model_dump(mode="json"))
        run_id = "daily-" + _hash({"snapshot": account.stable_json(), "market": market_hash, "cutoff": cutoff.isoformat(), "policy": policy_hash})[:24]
        blockers = self._gates(account, quotes, cutoff)
        if account.total_equity == 0:
            return self._result(run_id, account, cutoff, None, (), RunStatus.NO_CAPITAL, ("NO_CAPITAL",), quotes, market_hash, policy_hash)
        if blockers:
            status = RunStatus.BLOCKED_STALE_ACCOUNT if blockers[0].startswith("ACCOUNT") else RunStatus.BLOCKED_STALE_MARKET
            return self._result(run_id, account, cutoff, None, (), status, blockers, quotes, market_hash, policy_hash)
        selected = {ticker: quote for ticker, quote in quotes.items() if ticker in self.policies.universe.tickers}
        scores = [AlphaScore(ticker=ticker, score=max(Decimal("0"), quote.daily_return), confidence=Decimal("1"), expected_direction="BULLISH" if quote.daily_return > 0 else "NEUTRAL", risk_penalty=Decimal("0"), evidence_quality=Decimal("1"), model_source="deterministic-operational-signal") for ticker, quote in sorted(selected.items())]
        target = allocate_with_fallback(scores, {}, account, self.policies.risk, self.policies.allocation)
        # This bounded operational path classifies all fixture symbols explicitly;
        # it never claims PIT sector certification.
        approved = RiskEngine().approve(target, account, "NORMAL", self.policies.risk, sectors={ticker: "OPERATIONAL_UNCLASSIFIED" for ticker in selected}).approved
        reconciliation = ReconciliationEngine().reconcile(account, approved)
        orders = OrderPlanner().plan(account, reconciliation, selected, self.policies.execution, self.policies.risk, account.total_equity)
        projection = ProjectedPortfolioValidator().validate(account, orders, account.total_equity, self.policies.risk.min_cash_weight, self.policies.risk.max_position_weight, self.policies.risk.max_number_positions)
        failures = projection.violations
        status = RunStatus.DRAFT if orders and not failures else RunStatus.NO_ACTION if not failures else RunStatus.FAILED
        return self._result(run_id, account, cutoff, approved, orders if not failures else (), status, failures, selected, market_hash, policy_hash, reconciliation)

    def _gates(self, account: AccountSnapshot, quotes: dict[str, MarketSnapshot], cutoff: datetime) -> tuple[str, ...]:
        blockers: list[str] = []
        if account.freshness_state not in {FreshnessState.VERIFIED, FreshnessState.RECENT} or account.as_of > cutoff or (cutoff - account.as_of).total_seconds() > self.policies.data.account_snapshot_max_age_seconds or account.sync_state is not AccountSyncState.SYNCED:
            blockers.append("ACCOUNT_SNAPSHOT_STALE_OR_AFTER_CUTOFF")
        selected = {ticker: quote for ticker, quote in quotes.items() if ticker in self.policies.universe.tickers}
        if not selected:
            blockers.append("REQUIRED_OPERATIONAL_MARKET_DATA_UNAVAILABLE")
        for ticker, quote in selected.items():
            if quote.timestamp > cutoff or (cutoff - quote.timestamp).total_seconds() > self.policies.data.quote_max_age_seconds or quote.freshness_state not in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
                blockers.append(f"{ticker}:MARKET_STALE_OR_AFTER_CUTOFF")
        return tuple(blockers)

    def _result(self, run_id: str, account: AccountSnapshot, cutoff: datetime, target: TargetPortfolio | None, orders: tuple[OrderDraft, ...], status: RunStatus, blockers: tuple[str, ...], quotes: dict[str, MarketSnapshot], market_hash: str, policy_hash: str, reconciliation: ReconciliationResult | None = None) -> DailyClosureResult:
        decision = DailyDecision(run_id=run_id, as_of=cutoff, account_snapshot_status=account.freshness_state, account_sync_state=account.sync_state, market_data_status=FreshnessState.VERIFIED if not blockers else FreshnessState.STALE, regime="OPERATIONAL_DATA_PLANE", target_portfolio=target, orders=orders, warnings=(f"market_data_snapshot_hash={market_hash}", "EXECUTION = MANUAL", "BROKER SUBMISSION = DISABLED"), blocked_reasons=blockers, overall_status=status)
        report = {"schema_version": "meridian-daily-closure.v1", "run_id": run_id, "analysis_time": cutoff.isoformat(), "information_cutoff": cutoff.isoformat(), "account_snapshot_time": account.as_of.isoformat(), "account_snapshot_hash": _hash(account.model_dump(mode="json")), "market_data_snapshot_hash": market_hash, "policy_hash": policy_hash, "output_hash": _hash(decision.model_dump(mode="json")), "status": status.value, "execution": "MANUAL", "broker_submission": "DISABLED", "provider_status": {ticker: quote.freshness_state.value for ticker, quote in quotes.items()}, "portfolio": target.model_dump(mode="json") if target else None, "current_holdings": [{"ticker": h.ticker, "quantity": str(h.quantity), "market_value": str(h.market_value)} for h in account.holdings], "orders": [order.model_dump(mode="json") for order in orders], "reconciliation": {"status": reconciliation.status.value, "warnings": list(reconciliation.warnings)} if reconciliation else None, "blocked_reasons": list(blockers), "audit": {"raw_account_persisted": False, "credentials_persisted": False, "later_snapshots_mutate_run": False}, "research_note": "Operational observations are not PIT-certified research or execution quotes."}
        return DailyClosureResult(decision, report)


def persist_run_report(report: dict[str, object], paths: RuntimePaths) -> tuple[Path, Path]:
    """One writer for completed analysis and rejected-input diagnostics."""
    paths.ensure_directories()
    as_of = datetime.fromisoformat(str(report["analysis_time"]))
    directory = paths.reports / as_of.date().isoformat() / str(report["run_id"])
    directory.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = directory / "daily.json", directory / "daily.md"
    temporary = json_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(json_path)
    readiness = report.get("readiness", {})
    readiness = readiness if isinstance(readiness, dict) else {}
    lines = ["# Meridian daily research report", "", f"Run ID: `{report['run_id']}`",
             f"Runtime: **{report.get('runtime_status', 'UNKNOWN')}**; Analysis: **{report['status']}**",
             "", "## Recommendation readiness", "",
             f"Recommendation: **{readiness.get('recommendation_readiness', 'UNKNOWN')}**",
             f"Research: **{readiness.get('research_readiness', 'UNKNOWN')}**",
             f"Manual execution: **{readiness.get('manual_execution_readiness', 'BLOCKED')}**",
             "", "EXECUTION = MANUAL", "BROKER SUBMISSION = DISABLED", "",
             "## Blockers", ""]
    blockers = list(report.get("blocked_reasons", [])) + list(readiness.get("blockers", []))  # type: ignore[arg-type]
    lines.extend(f"- {item}" for item in dict.fromkeys(blockers))
    lines.extend(["", "## Next actions", ""])
    lines.extend(f"- {item}" for item in report.get("next_actions", []))  # type: ignore[union-attr]
    lines.extend(["", "## Research-only draft — NOT AUTHORIZED FOR MANUAL ENTRY", ""])
    orders = report.get("orders", [])
    if isinstance(orders, list):
        lines.extend(f"- {order['side']} {order['quantity']} {order['ticker']} @ {order.get('preferred_limit')}" for order in orders if isinstance(order, dict))
    temporary_md = markdown_path.with_suffix(".tmp")
    temporary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary_md.replace(markdown_path)
    return json_path, markdown_path


def persist_report(result: DailyClosureResult, paths: RuntimePaths) -> DailyClosureResult:
    json_path, markdown_path = persist_run_report(result.report, paths)
    return DailyClosureResult(result.decision, result.report, json_path, markdown_path)
