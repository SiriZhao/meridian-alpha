"""Safe daily closure from a sanitized Host snapshot to manual-only reports."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from meridian.allocation import allocate_with_fallback
from meridian.config import Policies
from meridian.daily_research import ResearchDecisionContext
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.market_identity import canonical_market_reference
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


def daily_run_id(account: AccountSnapshot, quotes: dict[str, MarketSnapshot], cutoff: datetime, policies: Policies) -> str:
    market = canonical_market_reference(quotes)
    trading_date = cutoff.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    return "daily-" + _hash({"snapshot": account.stable_json(), "market": market, "trading_date": trading_date, "policy": _hash(policies.models.model_dump(mode="json"))})[:24]


class DailyClosureService:
    """The only Stage-C closure service; it never enables broker submission."""

    def __init__(self, policies: Policies) -> None:
        self.policies = policies

    def run(self, account: AccountSnapshot, quotes: dict[str, MarketSnapshot], *, cutoff: datetime,
            research: ResearchDecisionContext | None = None, evaluated_at: datetime | None = None) -> DailyClosureResult:
        expected = daily_run_id(account, quotes, cutoff, self.policies)
        if research is not None and (research.parent_run_id != expected or research.analysis_cutoff != cutoff):
            raise ValueError("RESEARCH_DECISION_CONTEXT_MISMATCH")
        result = self._run(account, quotes, cutoff=cutoff, evaluated_at=evaluated_at)
        result.report["decision_context"] = {
            "research_run_id": research.research_run_id if research else None,
            "research_input_hash": research.input_hash if research else None,
            "research_status": research.status.value if research else "NOT_RUN",
            "authority": "ADVISORY_ONLY", "financial_parameters_source": "DETERMINISTIC_POLICY_AND_MARKET",
            "research": research.output.model_dump(mode="json") if research and research.output else None,
        }
        return result

    def _run(self, account: AccountSnapshot, quotes: dict[str, MarketSnapshot], *, cutoff: datetime, evaluated_at: datetime | None = None) -> DailyClosureResult:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("DAILY_CUTOFF_TIMEZONE_REQUIRED")
        market_hash = canonical_market_reference(quotes)
        policy_hash = _hash(self.policies.models.model_dump(mode="json"))
        run_id = daily_run_id(account, quotes, cutoff, self.policies)
        blockers = self._gates(account, quotes, cutoff, evaluated_at=evaluated_at)
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

    def _gates(self, account: AccountSnapshot, quotes: dict[str, MarketSnapshot], cutoff: datetime, *, evaluated_at: datetime | None = None) -> tuple[str, ...]:
        evaluated = evaluated_at or cutoff
        if evaluated.tzinfo is None or evaluated < cutoff:
            raise ValueError("DECISION_EVALUATION_TIME_INVALID")
        blockers: list[str] = []
        if account.freshness_state not in {FreshnessState.VERIFIED, FreshnessState.RECENT} or account.as_of > cutoff or (evaluated - account.as_of).total_seconds() > self.policies.data.account_snapshot_max_age_seconds or account.sync_state is not AccountSyncState.SYNCED:
            blockers.append("ACCOUNT_SNAPSHOT_STALE_OR_AFTER_CUTOFF")
        selected = {ticker: quote for ticker, quote in quotes.items() if ticker in self.policies.universe.tickers}
        if not selected:
            blockers.append("REQUIRED_OPERATIONAL_MARKET_DATA_UNAVAILABLE")
        for ticker, quote in selected.items():
            if quote.timestamp > cutoff or (evaluated - quote.timestamp).total_seconds() > self.policies.data.quote_max_age_seconds or quote.freshness_state not in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
                blockers.append(f"{ticker}:MARKET_STALE_OR_AFTER_CUTOFF")
        return tuple(blockers)

    def _result(self, run_id: str, account: AccountSnapshot, cutoff: datetime, target: TargetPortfolio | None, orders: tuple[OrderDraft, ...], status: RunStatus, blockers: tuple[str, ...], quotes: dict[str, MarketSnapshot], market_hash: str, policy_hash: str, reconciliation: ReconciliationResult | None = None) -> DailyClosureResult:
        decision = DailyDecision(run_id=run_id, as_of=cutoff, account_snapshot_status=account.freshness_state, account_sync_state=account.sync_state, market_data_status=FreshnessState.VERIFIED if not blockers else FreshnessState.STALE, regime="OPERATIONAL_DATA_PLANE", target_portfolio=target, orders=orders, warnings=(f"market_data_snapshot_hash={market_hash}", "EXECUTION = MANUAL", "BROKER SUBMISSION = DISABLED"), blocked_reasons=blockers, overall_status=status)
        report = {"schema_version": "meridian-daily-closure.v1", "run_id": run_id, "analysis_time": cutoff.isoformat(), "information_cutoff": cutoff.isoformat(), "account_snapshot_time": account.as_of.isoformat(), "account_snapshot_hash": _hash(account.model_dump(mode="json")), "market_data_snapshot_hash": market_hash, "policy_hash": policy_hash, "output_hash": _hash(decision.model_dump(mode="json")), "status": status.value, "execution": "MANUAL", "broker_submission": "DISABLED", "provider_status": {ticker: quote.freshness_state.value for ticker, quote in quotes.items()}, "portfolio": target.model_dump(mode="json") if target else None, "current_holdings": [{"ticker": h.ticker, "quantity": str(h.quantity), "market_value": str(h.market_value)} for h in account.holdings], "orders": [order.model_dump(mode="json") for order in orders], "reconciliation": {"status": reconciliation.status.value, "warnings": list(reconciliation.warnings)} if reconciliation else None, "blocked_reasons": list(blockers), "audit": {"raw_account_persisted": False, "credentials_persisted": False, "later_snapshots_mutate_run": False}, "research_note": "Operational observations are not PIT-certified research or execution quotes."}
        return DailyClosureResult(decision, report)


def publish_staged_report(staged: Path, destination: Path) -> None:
    """Publish a fully-written report without weakening failure semantics.

    Normal runtimes use an atomic rename. Some Windows EFS/AppContainer report
    directories allow creation but reject a rename with WinError 17. A daily run
    id makes the destination unique, so only in that case we create the final
    file exclusively, fsync it, and verify its content. Existing output is never
    overwritten and all other publication failures remain visible to the caller.
    """
    try:
        staged.replace(destination)
        return
    except OSError as error:
        if (getattr(error, "winerror", None) != 17 and getattr(error, "errno", None) != 17) or destination.exists():
            raise

    content = staged.read_bytes()
    with destination.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    if destination.read_bytes() != content:
        raise OSError("report publication verification failed")


def persist_run_report(report: dict[str, object], paths: RuntimePaths) -> tuple[Path, Path]:
    """One writer for completed analysis and rejected-input diagnostics."""
    paths.ensure_directories()
    as_of = datetime.fromisoformat(str(report["analysis_time"]))
    directory = paths.reports / as_of.date().isoformat() / str(report["run_id"])
    directory.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = directory / "daily.json", directory / "daily.md"
    temporary = json_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    publish_staged_report(temporary, json_path)
    readiness = report.get("readiness", {})
    readiness = readiness if isinstance(readiness, dict) else {}
    forward = report.get("forward_evidence", {})
    forward = forward if isinstance(forward, dict) else {}
    forward_summary = forward.get("summary", {})
    forward_summary = forward_summary if isinstance(forward_summary, dict) else {}
    startup = report.get("startup_diagnostics", {})
    startup = startup if isinstance(startup, dict) else {}
    environment = startup.get("environment", {})
    environment = environment if isinstance(environment, dict) else {}
    cache = startup.get("cache", {})
    cache = cache if isinstance(cache, dict) else {}
    provider = startup.get("data_provider", {})
    provider = provider if isinstance(provider, dict) else {}
    market_status = startup.get("market_status", {})
    market_status = market_status if isinstance(market_status, dict) else {}
    research_universe = report.get("research_universe", {})
    research_universe = research_universe if isinstance(research_universe, dict) else {}
    retrieval = report.get("data_auto_retrieval", {})
    retrieval = retrieval if isinstance(retrieval, dict) else {}
    lines = ["# Meridian daily research report", "", f"Run ID: `{report['run_id']}`",
             f"Environment: **{environment.get('status', report.get('runtime_status', 'UNKNOWN'))}**",
             f"Cache: **{cache.get('status', 'UNKNOWN')}** ({cache.get('error_code') or 'healthy'})",
             f"Data Provider: **{provider.get('status', 'NOT_RUN')}**; lanes: {', '.join(provider.get('selected_lanes', [])) or 'NONE'}",
             f"Market Status: **{market_status.get('status', 'UNKNOWN')}**",
             f"Execution Mode: **{startup.get('execution_mode', report.get('execution_mode', 'SAFE_ANALYSIS'))}**",
             f"Runtime: **{report.get('runtime_status', 'UNKNOWN')}**; Analysis: **{report['status']}**",
             f"Forward evidence: **{forward.get('status', 'NOT_RUN')}**; maturity: **{forward_summary.get('maturity_status', 'UNKNOWN')}**; samples: {forward_summary.get('sample_count', 0)}.",
             f"Account freshness: **{readiness.get('account_snapshot_freshness', 'UNKNOWN')}**; "
             f"Market freshness: **{readiness.get('market_data_freshness', 'UNKNOWN')}**",
             f"Research invocation: **{report.get('research_status', 'NOT_RUN')}**; "
             f"Decision: **{readiness.get('decision_pipeline_status', 'NOT_RUN')}**",
             f"Research universe: **{research_universe.get('mode', 'full')}**; "
             f"eligible {research_universe.get('original_count', 0)} -> "
             f"research {research_universe.get('research_count', 0)} -> "
             f"deep analysis {research_universe.get('deep_analysis_count', 0)}",
             "", "## Data auto-retrieval", "",
             f"Initial completeness: **{retrieval.get('initial_completeness', 'NOT_RUN')}**",
             f"Final completeness: **{retrieval.get('final_completeness', 'NOT_RUN')}**",
             f"Quality: **{retrieval.get('quality_grade', 'NOT_RUN')}** "
             f"({retrieval.get('quality_score', 0)}/100)",
             f"Requirements: {retrieval.get('requirements', 0)}; "
             f"retrieved: {retrieval.get('retrieved', 0)}; "
             f"sources: {retrieval.get('source_count', 0)}.",
             f"Unresolved blocking fields: "
             f"{', '.join(retrieval.get('blocking_missing', [])) or 'none'}",
             "", "## Recommendation readiness", "",
             f"Recommendation: **{readiness.get('recommendation_readiness', 'UNKNOWN')}**",
             f"Research: **{readiness.get('research_readiness', 'UNKNOWN')}**",
             f"Manual execution: **{readiness.get('manual_execution_readiness', 'BLOCKED')}**",
             "", "EXECUTION = MANUAL", "BROKER SUBMISSION = DISABLED", "",
             ""]
    idempotency = report.get("idempotency", {})
    if isinstance(idempotency, dict):
        raw_blockers = report.get("blocked_reasons", [])
        blockers_for_reason = raw_blockers if isinstance(raw_blockers, list) else []
        lines.extend([
            "## Idempotency", "",
            f"Status: **{idempotency.get('status', 'NOT_RUN')}**",
            f"Attempted run: `{idempotency.get('attempted_run_id', report.get('run_id', 'UNKNOWN'))}`",
            f"Authoritative existing run: `{idempotency.get('authoritative_existing_run_id', 'NONE')}`",
            f"Reason: **{blockers_for_reason[0] if blockers_for_reason else 'NONE'}**",
            f"Current-run ledger mutation: **{'YES' if idempotency.get('ledger_mutated_current_run') else 'NO'}**",
            "",
        ])
    lines.extend(["## Blockers", ""])
    blockers = list(report.get("blocked_reasons", [])) + list(readiness.get("blockers", []))  # type: ignore[arg-type]
    lines.extend(f"- {item}" for item in dict.fromkeys(blockers))
    snapshot = report.get("snapshot_provenance", {})
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    lines.extend(["", "## Input verification", "",
                  f"Account freshness: **{readiness.get('account_snapshot_freshness', 'UNKNOWN')}**; "
                  f"novelty: **{snapshot.get('novelty', 'UNKNOWN')}**; "
                  f"age seconds: {snapshot.get('age_seconds', 'UNKNOWN')}.",
                  f"Account provenance: **{readiness.get('account_provenance', 'UNKNOWN')}**; "
                  f"diagnostic: {snapshot.get('code', 'UNKNOWN')}.",
                  f"Market freshness: **{readiness.get('market_data_freshness', 'UNKNOWN')}**; "
                  f"mode: {report.get('data_mode', 'NOT_RUN')}."])
    lines.extend(["", "## Operator stages", "", "| Stage | Status |", "| --- | --- |"])
    for label, key in (("Market", "data_status"), ("Account", "portfolio_status"),
                       ("Research", "research_status"), ("Decision", "status")):
        lines.append(f"| {label} | {report.get(key, 'NOT_RUN')} |")
    lines.extend(["", "## Gates", ""])
    gates = report.get("gates", [])
    if isinstance(gates, list) and gates:
        lines.extend(f"- {gate['gate']}: **{gate['status']}** — {gate['reason']}"
                     for gate in gates if isinstance(gate, dict))
    else:
        lines.append("NOT_RUN: upstream inputs unavailable; no authority issued.")
    research = report.get("research", {})
    if isinstance(research, dict):
        diagnostics = research.get("provider_diagnostics", {})
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        structured = research.get("structured_response", {})
        structured = structured if isinstance(structured, dict) else {}
        context = research.get("context", {})
        context = context if isinstance(context, dict) else {}
        lines.extend(["", "## Research (MODEL_INFERENCE; advisory only)", "",
                      f"Provider/model: {research.get('provider', 'NOT_RUN')}/{research.get('model', 'NOT_RUN')}; "
                      f"provider evidence: {research.get('provenance', 'NONE')}; "
                      f"attempts: {research.get('attempts', 0)}; "
                      f"diagnostic: {research.get('error_code') or 'none'}.",
                      f"Auth mode: **{diagnostics.get('auth_mode', 'CHATGPT_MANAGED_CODEX')}**; "
                      f"reasoning: **{diagnostics.get('reasoning_effort', 'medium')}**; "
                      f"schema: **{'PASS' if diagnostics.get('schema_valid') else 'FAIL'}**; "
                      f"elapsed: **{diagnostics.get('elapsed_ms', 0)} ms**.",
                      f"Research status: **{context.get('status', 'NOT_RUN')}**; "
                      f"recommendation: **{structured.get('recommended_action', 'NO_ACTION')}**; "
                      f"confidence: **{structured.get('confidence', 'NOT_AVAILABLE')}**."])
        output = context.get("output") if isinstance(context, dict) else None
        if isinstance(output, dict):
            # Indented text renders model prose as literal content, never links/HTML.
            for item in output.get("results", []):
                lines.append("")
                lines.extend("    " + line for line in
                             (str(item.get("ticker")) + ": " + str(item.get("thesis"))).splitlines())
    intelligence = report.get("research_intelligence", {})
    intelligence = intelligence if isinstance(intelligence, dict) else {}
    if intelligence:
        confidence = intelligence.get("confidence", {})
        confidence = confidence if isinstance(confidence, dict) else {}
        primary = intelligence.get("primary", {})
        primary = primary if isinstance(primary, dict) else {}
        skeptic = intelligence.get("skeptic", {})
        skeptic = skeptic if isinstance(skeptic, dict) else {}
        scenarios = intelligence.get("scenarios", {})
        scenarios = scenarios if isinstance(scenarios, dict) else {}
        synthesis = intelligence.get("synthesis", {})
        synthesis = synthesis if isinstance(synthesis, dict) else {}
        lines.extend([
            "", "## Research intelligence (advisory only)", "",
            f"Research status: **{intelligence.get('research_state', 'NOT_RUN')}**; "
            f"Decision status: **{intelligence.get('decision_state', 'NOT_RUN')}**; "
            f"Execution status: **{intelligence.get('execution_state', 'BLOCKED')}**.",
            f"Research data: **{intelligence.get('research_data_status', 'UNKNOWN')}**; "
            f"Execution data: **{intelligence.get('execution_data_status', 'UNKNOWN')}**.",
            f"Evidence coverage: **{len(intelligence.get('evidence', [])) if isinstance(intelligence.get('evidence', []), list) else 0}**; "
            f"system confidence: **{confidence.get('system_confidence', 'NOT_AVAILABLE')}**; "
            f"LLM self-confidence: **{confidence.get('llm_self_confidence', 'NOT_AVAILABLE')}**.",
            f"Primary thesis (GPT OPINION): {synthesis.get('primary_thesis') or primary.get('thesis') or 'GPT reasoning unavailable.'}",
            f"Counter-thesis (GPT OPINION): {', '.join(skeptic.get('challenges', [])) if isinstance(skeptic.get('challenges', []), list) else 'not available'}",
            f"What changed: **{intelligence.get('thesis_change', 'UNKNOWN')}**.",
            f"Disagreement score: **{intelligence.get('disagreement_score', 'NOT_AVAILABLE')}**.",
            "FACT = normalized structured evidence; MODEL INFERENCE = deterministic analytics; GPT OPINION = schema-validated advisory reasoning.",
        ])
        if scenarios:
            lines.append("Bull/Base/Bear scenarios (GPT OPINION):")
            for label in ("bull", "base", "bear"):
                scenario = scenarios.get(label, {})
                if isinstance(scenario, dict):
                    lines.append(
                        f"- {label.title()}: {scenario.get('probability', 'UNKNOWN')} — {scenario.get('description', '')}"
                    )
        lines.append(
            "Execution availability remains independently gated. GPT research has no order, price, sizing, or broker authority."
        )
    lines.extend(["", "## Next actions", ""])
    lines.extend(f"- {item}" for item in report.get("next_actions", []))  # type: ignore[union-attr]
    lines.extend(["", "## Research-only draft — NOT AUTHORIZED FOR MANUAL ENTRY", ""])
    orders = report.get("orders", [])
    if isinstance(orders, list):
        lines.extend(f"- {order['side']} {order['quantity']} {order['ticker']} @ {order.get('preferred_limit')}" for order in orders if isinstance(order, dict))
    temporary_md = markdown_path.with_suffix(".tmp")
    temporary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    publish_staged_report(temporary_md, markdown_path)
    return json_path, markdown_path


def persist_report(result: DailyClosureResult, paths: RuntimePaths) -> DailyClosureResult:
    json_path, markdown_path = persist_run_report(result.report, paths)
    return DailyClosureResult(result.decision, result.report, json_path, markdown_path)
