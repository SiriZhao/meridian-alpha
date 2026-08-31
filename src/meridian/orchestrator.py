"""Strict, fail-closed daily decision orchestration."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from meridian.allocation import allocate_with_fallback
from meridian.alpha_fusion import fuse, fuse_production_decision
from meridian.audit import AuditStore
from meridian.config import Policies
from meridian.market import MarketDataProvider, feature_set
from meridian.orders import OrderPlanner, ProjectedPortfolioValidator, attach_limit_prices
from meridian.pipeline import ResearchPipelineMode, ResearchPipelineService
from meridian.reconciliation import ReconciliationEngine
from meridian.research import ResearchEngine, ResearchOutcome
from meridian.risk import RiskEngine
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    AlphaScore,
    DailyDecision,
    FreshnessState,
    ProductionAlphaDecision,
    RunStatus,
    TargetPortfolio,
)
from meridian.security import DevelopmentSecurityMetadataRegistry
from meridian.valuation import ValuedAccountState


class DailyOrchestrator:
    def __init__(
        self,
        policies: Policies,
        market: MarketDataProvider,
        research: ResearchEngine,
        audit: AuditStore | None = None,
    ) -> None:
        self.policies = policies
        self.market = market
        self.research = research
        self.audit = audit

    def run(
        self, account_snapshot: AccountSnapshot, run_date: datetime, mode: str = "daily"
    ) -> DailyDecision:
        _ = mode
        if run_date.tzinfo is None or run_date.utcoffset() is None:
            raise ValueError("run_date must be timezone-aware")
        run_id = f"run_{uuid4().hex}"
        if account_snapshot.as_of > run_date:
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    FreshnessState.UNKNOWN,
                    "UNKNOWN",
                    RunStatus.FAILED,
                    blocked_reasons=("AccountSnapshot is after the requested analysis time.",),
                )
            )
        age = (run_date - account_snapshot.as_of).total_seconds()
        if (
            account_snapshot.sync_state is AccountSyncState.UNAVAILABLE
            or account_snapshot.freshness_state in {FreshnessState.STALE, FreshnessState.UNKNOWN}
            or age > self.policies.data.account_snapshot_max_age_seconds
        ):
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    FreshnessState.UNKNOWN,
                    "UNKNOWN",
                    RunStatus.BLOCKED_STALE_ACCOUNT,
                    blocked_reasons=(
                        "Current AccountSnapshot freshness or timestamp age cannot be verified.",
                    ),
                )
            )
        if account_snapshot.total_equity == 0:
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    FreshnessState.UNKNOWN,
                    "NO_CAPITAL",
                    RunStatus.NO_CAPITAL,
                    warnings=("Current account has no capital. No orders generated.",),
                )
            )
        quotes = {}
        technicals = {}
        errors = []
        market_tickers = tuple(
            sorted(
                set(self.policies.universe.tickers) | {h.ticker for h in account_snapshot.holdings}
            )
        )
        for ticker in market_tickers:
            try:
                quote = self.market.get_market_snapshot(ticker, run_date)
                history = self.market.get_history(
                    ticker, datetime(1900, 1, 1, tzinfo=run_date.tzinfo), run_date, "1d"
                )
                daily = feature_set(history, run_date).get("daily_return")
                if daily is None:
                    raise ValueError("missing point-in-time technical feature")
                quotes[ticker] = quote
                technicals[ticker] = daily
            except Exception as error:
                errors.append(f"{ticker}: {type(error).__name__}")
        try:
            benchmark = self.market.get_benchmark_snapshot()
        except Exception as error:
            benchmark = None
            errors.append(f"benchmark: {type(error).__name__}")
        if errors:
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    FreshnessState.UNKNOWN,
                    "UNKNOWN",
                    RunStatus.DRAFT,
                    warnings=tuple(errors),
                    blocked_reasons=(
                        "Market data is incomplete; executable order output is blocked.",
                    ),
                )
            )
        all_quotes = list(quotes.values()) + [benchmark]
        assert benchmark is not None
        too_old = any(
            (run_date - q.timestamp).total_seconds() > self.policies.data.quote_max_age_seconds
            for q in all_quotes
        )
        if (
            any(q.timestamp > run_date for q in all_quotes)
            or too_old
            or any(
                q.freshness_state in {FreshnessState.STALE, FreshnessState.UNKNOWN}
                for q in all_quotes
            )
        ):
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    FreshnessState.STALE,
                    "UNKNOWN",
                    RunStatus.BLOCKED_STALE_MARKET,
                    blocked_reasons=("A required market quote is future, stale, or unverifiable.",),
                )
            )
        market_status = (
            FreshnessState.RECENT
            if any(q.freshness_state is FreshnessState.RECENT for q in all_quotes)
            else FreshnessState.VERIFIED
        )
        try:
            valued = ValuedAccountState.from_snapshot(
                account_snapshot, quotes, self.policies.data.nav_discrepancy_tolerance
            )
        except Exception as error:
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    market_status,
                    "UNKNOWN",
                    RunStatus.DRAFT,
                    warnings=(f"valuation: {type(error).__name__}",),
                    blocked_reasons=(
                        "Current marked valuation is unavailable; executable output is blocked.",
                    ),
                )
            )
        scores = []
        research_errors = []
        attempted_research = 0
        successful_research = 0
        research_outcomes: list[ResearchOutcome] = []
        research_tickers = tuple(self.policies.universe.tickers)
        candidate_selector = getattr(self.research, "candidate_tickers", None)
        if callable(candidate_selector):
            try:
                selected_candidates = candidate_selector(
                    research_tickers,
                    tuple(holding.ticker for holding in account_snapshot.holdings),
                )
                if not isinstance(selected_candidates, (list, tuple)):
                    raise TypeError("candidate selector returned a non-iterable result")
                research_tickers = tuple(str(ticker) for ticker in selected_candidates)
            except Exception as error:  # noqa: BLE001 - budget failure is fail-closed
                return self._record(
                    self._decision(
                        run_id,
                        run_date,
                        account_snapshot,
                        market_status,
                        "UNKNOWN",
                        RunStatus.DRAFT,
                        warnings=(f"research_budget: {type(error).__name__}",),
                        blocked_reasons=(
                            "Research budget cannot produce a valid candidate set.",
                        ),
                    )
                )
        if isinstance(self.research, ResearchPipelineService):
            feature_inputs = {
                ticker: {"feature_timestamp": run_date, "momentum": technicals[ticker]}
                for ticker in research_tickers
                if ticker in technicals
            }
            pipeline_result = self.research.run(
                research_tickers,
                run_date,
                feature_inputs,
                existing_holdings=tuple(holding.ticker for holding in account_snapshot.holdings),
                mode=ResearchPipelineMode.LIVE,
                market_contexts={
                    ticker: {"quote": quotes[ticker].model_dump(mode="json")}
                    for ticker in research_tickers
                    if ticker in quotes
                },
            )
            attempted_research = len(pipeline_result.candidate_set.candidates)
            for certificate in pipeline_result.certified_signals:
                scores.append(fuse(certificate, technicals[certificate.ticker]))
            successful_research = len(pipeline_result.certified_signals)
            research_errors.extend(pipeline_result.warnings)
            research_errors.extend(
                f"{outcome.ticker}:{outcome.error_code or outcome.status.value}"
                for outcome in pipeline_result.grounded_outcomes
                if not outcome.available
            )
        else:
            for ticker in research_tickers:
                attempted_research += 1
                try:
                    result = self.research.analyze(
                        ticker, run_date, {"quote": quotes[ticker].model_dump(mode="json")}
                    )
                    if isinstance(result, ResearchOutcome):
                        research_outcomes.append(result)
                        if not result.available or result.certified_signal is None:
                            research_errors.append(
                                f"{ticker}: {result.error_code or result.status.value}"
                            )
                            continue
                        certificate = result.certified_signal
                    else:
                        research_errors.append(f"{ticker}:DIRECT_AGENT_SIGNAL_FORBIDDEN")
                        continue
                    scores.append(fuse(certificate, technicals[ticker]))
                    successful_research += 1
                except Exception as error:
                    research_errors.append(f"{ticker}: {type(error).__name__}")
        minimum_coverage = (
            self.policies.models.research.minimum_research_coverage
            if self.policies.models.research is not None
            else Decimal("1")
        )
        coverage = (
            (Decimal(successful_research) / Decimal(attempted_research))
            if attempted_research
            else Decimal("0")
        )
        if research_errors or coverage < minimum_coverage:
            return self._record(
                self._decision(
                    run_id,
                    run_date,
                    account_snapshot,
                    market_status,
                    "UNKNOWN",
                    RunStatus.DRAFT,
                    warnings=tuple(research_errors)
                    + (f"research_coverage={coverage}",)
                    + (f"research_candidates={len(research_tickers)}/{len(self.policies.universe.tickers)}",),
                    blocked_reasons=(
                        "Research is incomplete; executable order output is blocked.",
                    ),
                )
            )
        target = allocate_with_fallback(
            scores,
            self.market.get_volatility_context(),
            account_snapshot,
            self.policies.risk,
            self.policies.allocation,
        )
        regime = "RISK_OFF" if benchmark.daily_return < Decimal("-0.03") else "NORMAL"
        registry = DevelopmentSecurityMetadataRegistry()
        metadata = {
            t: registry.get(t)
            for t in set(self.policies.universe.tickers)
            | {h.ticker for h in account_snapshot.holdings}
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}
        risk = RiskEngine().approve(
            target, account_snapshot, regime, self.policies.risk, metadata=metadata
        )
        reconciliation = ReconciliationEngine().reconcile(account_snapshot, risk.approved, valued)
        drafts = OrderPlanner().plan(
            account_snapshot,
            reconciliation,
            quotes,
            self.policies.execution,
            self.policies.risk,
            valued.decision_nav,
        )
        priced = attach_limit_prices(drafts, quotes, self.policies.execution)
        projection = ProjectedPortfolioValidator().validate(
            account_snapshot,
            priced,
            valued.decision_nav,
            self.policies.risk.min_cash_weight,
            self.policies.risk.max_position_weight,
            self.policies.risk.max_number_positions,
            valued,
            {k: v.sector for k, v in metadata.items() if v.sector},
            self.policies.risk.max_sector_weight,
        )
        warnings = (
            list(risk.modifications)
            + list(reconciliation.warnings)
            + [f"research_coverage={coverage}"]
            + [f"research_candidates={len(research_tickers)}/{len(self.policies.universe.tickers)}"]
        )
        blocked = list(risk.violations)
        if valued.discrepancy_exceeds_tolerance:
            warnings.append("NAV discrepancy exceeds configured tolerance.")
        if not projection.valid:
            blocked.extend(projection.violations)
        status = (
            RunStatus.READY_FOR_MANUAL_ENTRY
            if account_snapshot.sync_state is AccountSyncState.SYNCED
            and priced
            and projection.valid
            and not valued.discrepancy_exceeds_tolerance
            and all(o.status is RunStatus.READY_FOR_MANUAL_ENTRY for o in priced)
            else (
                RunStatus.NO_ACTION
                if not priced and not blocked and not valued.discrepancy_exceeds_tolerance
                else RunStatus.DRAFT
            )
        )
        decision = DailyDecision(
            run_id=run_id,
            as_of=run_date,
            account_snapshot_status=account_snapshot.freshness_state,
            account_sync_state=account_snapshot.sync_state,
            market_data_status=market_status,
            regime=regime,
            target_portfolio=risk.approved,
            orders=priced,
            warnings=tuple(warnings),
            blocked_reasons=tuple(blocked),
            overall_status=status,
        )
        if self.audit is not None and research_outcomes:
            self.audit.write_research_outcomes(run_id, research_outcomes)
        return self._record(decision)

    @staticmethod
    def _decision(
        run_id, as_of, account, market_status, regime, status, warnings=(), blocked_reasons=()
    ):
        return DailyDecision(
            run_id=run_id,
            as_of=as_of,
            account_snapshot_status=account.freshness_state,
            account_sync_state=account.sync_state,
            market_data_status=market_status,
            regime=regime,
            warnings=warnings,
            blocked_reasons=blocked_reasons,
            overall_status=status,
        )

    def _record(self, decision):
        if self.audit is not None:
            self.audit.write_decision(decision)
        return decision


class DailyAnalysisService:
    """Single application boundary shared by CLI, MCP, and tests."""

    def __init__(self, orchestrator: DailyOrchestrator | None, policies: Policies | None = None):
        self.orchestrator = orchestrator
        self.policies = policies

    def run(self, account_snapshot: AccountSnapshot, run_date: datetime) -> DailyDecision:
        if run_date.tzinfo is None or run_date.utcoffset() is None:
            raise ValueError("run_date must be timezone-aware")
        if account_snapshot.as_of > run_date:
            return DailyDecision(
                run_id=f"service_{uuid4().hex}",
                as_of=run_date,
                account_snapshot_status=FreshnessState.UNKNOWN,
                account_sync_state=account_snapshot.sync_state,
                market_data_status=FreshnessState.UNKNOWN,
                regime="UNKNOWN",
                blocked_reasons=("AccountSnapshot is after requested analysis time.",),
                overall_status=RunStatus.FAILED,
            )
        if (
            self.policies is not None
            and (run_date - account_snapshot.as_of).total_seconds()
            > self.policies.data.account_snapshot_max_age_seconds
        ):
            return DailyDecision(
                run_id=f"service_{uuid4().hex}",
                as_of=run_date,
                account_snapshot_status=FreshnessState.STALE,
                account_sync_state=account_snapshot.sync_state,
                market_data_status=FreshnessState.UNKNOWN,
                regime="UNKNOWN",
                blocked_reasons=("Account snapshot exceeds configured age limit.",),
                overall_status=RunStatus.BLOCKED_STALE_ACCOUNT,
            )
        if (
            account_snapshot.sync_state is AccountSyncState.UNAVAILABLE
            or account_snapshot.freshness_state in {FreshnessState.STALE, FreshnessState.UNKNOWN}
        ):
            return DailyDecision(
                run_id=f"service_{uuid4().hex}",
                as_of=run_date,
                account_snapshot_status=account_snapshot.freshness_state,
                account_sync_state=account_snapshot.sync_state,
                market_data_status=FreshnessState.UNKNOWN,
                regime="UNKNOWN",
                blocked_reasons=("Account freshness cannot be verified.",),
                overall_status=RunStatus.BLOCKED_STALE_ACCOUNT,
            )
        if account_snapshot.total_equity == 0:
            return DailyDecision(
                run_id=f"service_{uuid4().hex}",
                as_of=run_date,
                account_snapshot_status=account_snapshot.freshness_state,
                account_sync_state=account_snapshot.sync_state,
                market_data_status=FreshnessState.UNKNOWN,
                regime="NO_CAPITAL",
                overall_status=RunStatus.NO_CAPITAL,
            )
        if self.orchestrator is None:
            return DailyDecision(
                run_id=f"service_{uuid4().hex}",
                as_of=run_date,
                account_snapshot_status=account_snapshot.freshness_state,
                account_sync_state=account_snapshot.sync_state,
                market_data_status=FreshnessState.UNKNOWN,
                regime="UNKNOWN",
                warnings=("No verified market-data provider is configured.",),
                blocked_reasons=("Market data unavailable.",),
                overall_status=RunStatus.BLOCKED_STALE_MARKET,
            )
        return self.orchestrator.run(account_snapshot, run_date)


class ProductionShadowResult:
    """Production-path shadow output; no order or broker side effects."""

    def __init__(
        self,
        *,
        run_id: str,
        decision_as_of: datetime,
        alpha_decisions: tuple[ProductionAlphaDecision, ...],
        alpha_scores: tuple[AlphaScore, ...],
        target_before_risk: TargetPortfolio,
        target_after_risk: TargetPortfolio,
        risk_violations: tuple[str, ...],
        reconciliation_status: RunStatus,
        reconciliation_warnings: tuple[str, ...],
    ) -> None:
        self.run_id = run_id
        self.decision_as_of = decision_as_of
        self.alpha_decisions = alpha_decisions
        self.alpha_scores = alpha_scores
        self.target_before_risk = target_before_risk
        self.target_after_risk = target_after_risk
        self.risk_violations = risk_violations
        self.reconciliation_status = reconciliation_status
        self.reconciliation_warnings = reconciliation_warnings
        self.authorization = "SHADOW / NOT AUTHORIZED FOR ENTRY"


class ProductionShadowOrchestrator:
    """One authoritative quant → AlphaFusion → allocation → risk → reconcile path."""

    def run(
        self,
        *,
        account_snapshot: AccountSnapshot,
        run_id: str,
        decision_as_of: datetime,
        certified_signals: dict[str, object],
        quant_scores: dict[str, Decimal],
        policy_hash: str,
        risk_policy,
        allocation_policy,
        market_state: dict[str, Decimal] | None = None,
        quant_inputs: dict[str, object] | None = None,
        response_hashes: dict[str, str] | None = None,
        dislocation_modifiers: dict[str, Decimal] | None = None,
        regime: str = "NORMAL",
    ) -> ProductionShadowResult:
        if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
            raise ValueError("production decision_as_of must be timezone-aware")
        if account_snapshot.as_of > decision_as_of:
            raise ValueError("production account snapshot is after decision cutoff")
        from meridian.authorization import CertifiedAgentSignal

        alpha_decisions: list[ProductionAlphaDecision] = []
        alpha_scores: list[AlphaScore] = []
        dislocation_modifiers = dislocation_modifiers or {}
        quant_inputs = quant_inputs or {}
        response_hashes = response_hashes or {}
        for ticker in sorted(certified_signals):
            signal = certified_signals[ticker]
            if not isinstance(signal, CertifiedAgentSignal):
                raise TypeError("production path requires CertifiedAgentSignal objects")
            quant = quant_scores.get(ticker)
            if quant is None:
                raise ValueError(f"missing real quant score: {ticker}")
            decision = fuse_production_decision(
                signal,
                run_id=run_id,
                quant_score=quant,
                policy_hash=policy_hash,
                quant_input=quant_inputs.get(ticker, {"ticker": ticker, "score": str(quant)}),
                response_artifact_hash=response_hashes.get(ticker),
                dislocation_modifier=dislocation_modifiers.get(ticker, Decimal("0")),
            )
            alpha_decisions.append(decision)
            alpha_scores.append(
                fuse(
                    signal,
                    quant,
                    dislocation_modifier=dislocation_modifiers.get(ticker, Decimal("0")),
                )
            )
        target = allocate_with_fallback(
            alpha_scores,
            market_state or {},
            account_snapshot,
            risk_policy,
            allocation_policy,
        )
        risk = RiskEngine().approve(target, account_snapshot, regime, risk_policy)
        reconciliation = ReconciliationEngine().reconcile(account_snapshot, risk.approved)
        return ProductionShadowResult(
            run_id=run_id,
            decision_as_of=decision_as_of,
            alpha_decisions=tuple(alpha_decisions),
            alpha_scores=tuple(alpha_scores),
            target_before_risk=target,
            target_after_risk=risk.approved,
            risk_violations=risk.violations,
            reconciliation_status=reconciliation.status,
            reconciliation_warnings=reconciliation.warnings,
        )
