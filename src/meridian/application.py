"""Canonical application facade: CLI/MCP call this, domain code stays below."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from meridian.audit import SCHEMA_VERSION, AuditStore
from meridian.config import load_forward_evidence_policy, load_policies
from meridian.daily_closure import (
    DailyClosureResult,
    DailyClosureService,
    daily_run_id,
    load_market_fixture,
    persist_run_report,
    publish_staged_report,
)
from meridian.daily_research import (
    DailyResearchInput,
    DailyResearchOutput,
    PublicResearchObservation,
    ResearchDecisionContext,
    ResearchProviderStatus,
    ResearchStageResult,
    SymbolResearch,
)
from meridian.forward_evidence import ForwardLedger, freeze_canonical_predictions
from meridian.forward_evidence import policy_hash as forward_policy_hash
from meridian.gpt_native_research import (
    ExecutionState,
    GPTNativeResearchOrchestrator,
    ResearchMemory,
    persist_research_trace,
)
from meridian.host_llm import HostJobStage, accept_result, create_job, load_job
from meridian.host_readiness import (
    ReadinessGateResult,
    ReadinessStatus,
    RecommendationReadiness,
    SnapshotDiagnostic,
    inspect_snapshot,
)
from meridian.intelligence import ResearchPacket
from meridian.intelligence_tools import dip_scout
from meridian.market_status import MarketStatus, market_status
from meridian.operational_data import FreshnessPolicy
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.paper import DEFAULT_ACCOUNT, DEFAULT_INITIAL_CASH, PaperLedger, PaperSettings
from meridian.portfolio_snapshot import PortfolioSnapshot
from meridian.research_agents.audit import write_research_audit
from meridian.research_agents.preparation import ResearchPreparationService
from meridian.research_stage import CanonicalResearchStage
from meridian.research_universe import ResearchUniverseScheduler
from meridian.run_health import persist_run_health
from meridian.runtime import RuntimePaths, policy_directory
from meridian.runtime_diagnostics import report as doctor_report
from meridian.runtime_io import run_lock
from meridian.schemas import MarketSnapshot, RunStatus
from meridian.shadow_evaluation import ShadowMode, ShadowResearchRunner
from meridian.temporal import ResearchTemporalContext


class MeridianApplicationService:
    """Thin canonical application layer; it owns no allocator, risk, or pricing logic."""

    def __init__(
        self,
        paths: RuntimePaths | None = None,
        *,
        research_stage: CanonicalResearchStage | None = None,
        research_universe_scheduler: ResearchUniverseScheduler | None = None,
    ) -> None:
        self.paths = paths or RuntimePaths.from_environment()
        self.research_stage = research_stage or CanonicalResearchStage()
        if (
            research_stage is None
            and getattr(self.research_stage, "preparation", None) is None
            and not bool(getattr(self.research_stage.provider, "_injected_runner", False))
        ):
            self.research_stage.preparation = ResearchPreparationService.from_runtime(self.paths)
        self.research_universe_scheduler = (
            research_universe_scheduler or ResearchUniverseScheduler()
        )
        self.native_research = GPTNativeResearchOrchestrator(
            memory=ResearchMemory(self.paths.data / "research" / "memory")
        )

    def version(self) -> dict[str, object]:
        try:
            project_version = importlib.metadata.version("meridian-alpha")
        except importlib.metadata.PackageNotFoundError:
            project_version = "UNAVAILABLE"
        return {
            "project_version": project_version,
            "python": sys.version.split()[0],
            "expected_python": "3.12",
            "supported": sys.version_info[:2] == (3, 12),
        }

    def paths_status(self) -> dict[str, str]:
        return self.paths.as_dict()

    def doctor(self) -> dict[str, object]:
        return doctor_report(self.paths)

    def init(self) -> dict[str, object]:
        self.paths.ensure_directories()
        existed = self.paths.db.exists()
        try:
            AuditStore(self.paths.db).migrate()
            with closing(
                sqlite3.connect(self.paths.db.resolve().as_uri() + "?mode=rw", uri=True)
            ) as connection:
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
        except (OSError, sqlite3.Error) as error:
            return {
                "status": "INIT_FAILED",
                "runtime_home": str(self.paths.home),
                "db_path": str(self.paths.db),
                "schema_version": None,
                "warnings": [type(error).__name__],
                "error_code": "MERIDIAN_DATABASE_INIT_FAILED",
                "category": "USER_FIXABLE",
                "next_step": "Check database permissions, locks and schema with doctor; preserve the existing database.",
            }
        return {
            "status": "INIT_ALREADY_COMPLETE" if existed else "INIT_COMPLETE",
            "runtime_home": str(self.paths.home),
            "db_path": str(self.paths.db),
            "schema_version": version or SCHEMA_VERSION,
            "created_dirs": sorted(self.paths.directories()),
            "warnings": [],
        }

    def snapshot_validate(self, path: Path) -> dict[str, object]:
        policies = load_policies(policy_directory())
        diagnostic, _ = inspect_snapshot(
            path, max_age_seconds=policies.data.account_snapshot_max_age_seconds
        )
        diagnostic = self._snapshot_novelty(diagnostic, claim=False)
        return {
            "valid": diagnostic.status is ReadinessStatus.PASS,
            "status": "PASS" if diagnostic.status is ReadinessStatus.PASS else "DEGRADED",
            "snapshot_provenance": diagnostic.model_dump(mode="json"),
            "sanitized": True,
        }

    def _snapshot_novelty(
        self, diagnostic: SnapshotDiagnostic, *, claim: bool
    ) -> SnapshotDiagnostic:
        if (
            diagnostic.status is not ReadinessStatus.PASS
            or diagnostic.snapshot_key is None
            or diagnostic.content_hash is None
        ):
            return diagnostic
        novelty = AuditStore(self.paths.db).snapshot_novelty(
            diagnostic.snapshot_key,
            diagnostic.content_hash,
            seen_at=diagnostic.checked_at.isoformat() if claim else None,
        )
        return diagnostic.model_copy(
            update={
                "novelty": novelty,
                **(
                    {
                        "status": ReadinessStatus.BLOCKED,
                        "code": "ACCOUNT_SNAPSHOT_REPLAYED"
                        if novelty == "REPLAYED"
                        else "ACCOUNT_SNAPSHOT_ID_CONFLICT",
                    }
                    if novelty != "NEW"
                    else {}
                ),
            }
        )

    def _rejected_snapshot(
        self,
        diagnostic: SnapshotDiagnostic,
        log_path: Path,
        startup: dict[str, object] | None = None,
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        run_id = "daily-" + uuid4().hex
        ready = RecommendationReadiness(
            runtime_health=ReadinessStatus.PASS,
            account_snapshot_status=diagnostic.status,
            account_snapshot_freshness=diagnostic.freshness,
            account_provenance=diagnostic.provenance_status,
            market_data_status=ReadinessStatus.NOT_RUN,
            market_data_freshness=ReadinessStatus.NOT_RUN,
            quote_certification_status=ReadinessStatus.BLOCKED,
            quote_kind="NOT_REQUESTED",
            input_mode=diagnostic.source_kind or "UNKNOWN",
        )
        directory = self.paths.reports / now.date().isoformat() / run_id
        payload: dict[str, object] = {
            "run_id": run_id,
            "analysis_time": now.isoformat(),
            "timestamp": now.isoformat(),
            "trading_date": now.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
            "status": "BLOCKED_STALE_ACCOUNT",
            "runtime_status": "PASS",
            "readiness": ready.model_dump(mode="json"),
            "snapshot_provenance": diagnostic.model_dump(mode="json"),
            "data_status": "NOT_RUN",
            "research_status": "NOT_RUN",
            "quant_status": "NOT_RUN",
            "risk_status": "NOT_RUN",
            "recommendation_status": "BLOCKED",
            "blocked_reasons": [diagnostic.code],
            "errors": [diagnostic.code],
            "warnings": [],
            "orders": [],
            "next_actions": [diagnostic.next_action],
            "provider_probes": {},
            "research": {
                "context": {"status": "NOT_RUN", "output": None, "authority": "ADVISORY_ONLY"},
                "provenance": "NONE",
                "attempts": 0,
                "error_code": "RESEARCH_UPSTREAM_BLOCKED",
                "next_action": diagnostic.next_action,
            },
            "decision_context": {"research_status": "NOT_RUN", "research": None},
            "gates": [
                ReadinessGateResult(
                    gate=name,
                    status=ReadinessStatus.NOT_RUN,
                    reason="Snapshot validation prevented evaluation",
                    evidence=(diagnostic.code,),
                ).model_dump(mode="json")
                for name in (
                    "ACCOUNT_READY",
                    "SECURITY_READY",
                    "MARKET_READY",
                    "RESEARCH_READY",
                    "QUOTE_READY",
                    "RISK_READY",
                    "RECONCILIATION_READY",
                )
            ],
            "manual_authority": {"status": "BLOCKED", "certificate_issued": False},
            "stages": [
                {
                    "stage": name,
                    "run_id": run_id,
                    "start": None,
                    "finish": None,
                    "duration_seconds": 0,
                    "status": "NOT_RUN",
                    "error_code": "UPSTREAM_SNAPSHOT_BLOCKED",
                    "next_action": diagnostic.next_action,
                }
                for name in ("market", "research", "decision")
            ],
            "execution": "MANUAL",
            "broker_submission": "DISABLED",
            "market_status": (startup or {}).get("market_status", {}),
            "execution_mode": "SAFE_ANALYSIS",
            "startup_diagnostics": startup or {},
            "safe_analysis": {"status": "BLOCKED_ACCOUNT_INPUT", "orders": [], "authority": "NONE"},
            "output_files": {
                "report_json": str(directory / "daily.json"),
                "report_markdown": str(directory / "daily.md"),
                "log": str(log_path),
            },
        }
        AuditStore(self.paths.db).write_readiness(
            run_id, now.isoformat(), str(payload["status"]), payload
        )
        return self._complete_report(payload)

    def daily(
        self,
        snapshot_path: Path | None,
        market_fixture: Path | None = None,
        *,
        research_live_enabled: bool = False,
    ) -> dict[str, object]:
        self.paths.ensure_directories()
        self.paths.preflight()
        invocation = uuid4().hex
        log_path = self.paths.logs / ("daily-" + invocation + ".log")
        logger = logging.getLogger("meridian.daily." + invocation)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.info("START invocation=%s config=%s", invocation, policy_directory())
        try:
            with run_lock(self.paths.locks, invocation):
                payload = self._daily(
                    snapshot_path, market_fixture, logger, log_path, research_live_enabled
                )
            logger.log(
                logging.ERROR if payload.get("runtime_status") == "FAILED" else logging.INFO,
                "run_id=%s runtime=%s error_code=%s",
                payload.get("run_id"),
                payload.get("runtime_status"),
                payload.get("error_code"),
            )
            return payload
        except (OSError, ValueError, sqlite3.Error):
            logger.error(
                "Daily failed; run doctor and validate input. Exception details omitted to protect account data."
            )
            raise
        finally:
            logger.info("END invocation=%s", invocation)
            logger.removeHandler(handler)
            handler.close()

    def _daily(
        self,
        snapshot_path: Path | None,
        market_fixture: Path | None,
        logger: logging.Logger,
        log_path: Path,
        research_live_enabled: bool,
    ) -> dict[str, object]:
        started = monotonic()
        logger.info("Database initialization and preflight started")
        initialized = self.init()
        if initialized["status"] == "INIT_FAILED":
            return {
                **initialized,
                "run_id": log_path.stem,
                "runtime_status": "FAILED",
                "readiness": RecommendationReadiness(
                    runtime_health=ReadinessStatus.FAILED
                ).model_dump(mode="json"),
                "errors": [initialized["error_code"]],
                "next_actions": [initialized["next_step"]],
                "output_files": {"log": str(log_path)},
            }
        preflight = self.doctor()
        if preflight["status"] == "FAIL":
            return {
                "status": "FAILED",
                "run_id": log_path.stem,
                "runtime_status": "FAILED",
                "error_code": "MERIDIAN_PREFLIGHT_FAILED",
                "diagnostics": preflight,
                "readiness": RecommendationReadiness(
                    runtime_health=ReadinessStatus.FAILED
                ).model_dump(mode="json"),
                "errors": ["MERIDIAN_PREFLIGHT_FAILED"],
                "next_actions": ["Resolve failed doctor checks."],
                "output_files": {"log": str(log_path)},
            }
        logger.info("Database status=%s", initialized["status"])
        policies = load_policies(policy_directory())
        initial_market = market_status(datetime.now(UTC))
        startup: dict[str, object] = {
            "environment": {
                "status": preflight["status"],
                "python": sys.version.split()[0],
                "runtime_home": str(self.paths.home),
            },
            "cache": preflight.get(
                "cache", {"status": "BLOCKED", "error_code": "CACHE_HEALTH_UNAVAILABLE"}
            ),
            "data_provider": {"status": "NOT_RUN", "selected_lanes": []},
            "market_status": initial_market.as_dict(),
            "execution_mode": "NORMAL"
            if initial_market.status is MarketStatus.OPEN
            else "SAFE_ANALYSIS",
        }
        snapshot, account = inspect_snapshot(
            snapshot_path, max_age_seconds=policies.data.account_snapshot_max_age_seconds
        )
        snapshot = self._snapshot_novelty(snapshot, claim=True)
        if snapshot.status is not ReadinessStatus.PASS or account is None:
            logger.warning("Snapshot rejected code=%s", snapshot.code)
            return self._rejected_snapshot(snapshot, log_path, startup)
        cutoff = datetime.now(UTC)
        market_started = cutoff
        logger.info(
            "Market retrieval started; mode=%s",
            "FIXTURE" if market_fixture else "OPERATIONAL_PUBLIC",
        )
        market_error: str | None = None
        if market_fixture:
            try:
                quotes = load_market_fixture(market_fixture)
            except (ValueError, UnicodeError):
                quotes = {}
                market_error = "MARKET_FIXTURE_INVALID"
            except OSError:
                quotes = {}
                market_error = "MARKET_FIXTURE_UNAVAILABLE"
            partial_quotes = dict(quotes)
            research_quotes = dict(quotes)
            provenance: dict[str, object] = {
                "data_mode": "FIXTURE",
                "data_quality_mode": "DATA_DEGRADED",
                "information_cutoff": cutoff.isoformat(),
                "provider_health": {
                    ticker: {"primary": "FIXTURE", "secondary": "NOT_USED"} for ticker in quotes
                },
                "cache": {},
                "provider_conflicts": {},
                "symbols_missing": {},
            }
        else:
            symbols = set(policies.universe.tickers) | {
                holding.ticker for holding in account.holdings
            }
            operational = OperationalMarketSnapshotService.from_runtime(
                self.paths,
                policy=FreshnessPolicy(
                    quote_max_age_seconds=policies.data.quote_max_age_seconds,
                    account_max_age_seconds=policies.data.account_snapshot_max_age_seconds,
                ),
            ).build(symbols, analysis_time=cutoff, live=True)
            cutoff = operational.information_cutoff
            research_quotes = dict(operational.research_quotes)
            partial_quotes = dict(research_quotes)
            quotes = operational.quotes if not operational.missing_symbols else {}
            provenance = {
                "data_mode": operational.data_mode,
                "data_quality_mode": operational.data_quality_mode,
                "market_snapshot_hash": operational.snapshot_hash,
                "information_cutoff": operational.information_cutoff.isoformat(),
                "provider_health": operational.provider_health,
                "provider_probes": operational.provider_probes,
                "cache": operational.cache,
                "provider_conflicts": operational.conflicts,
                "symbols_missing": operational.missing_symbols,
                "research_pit": "BLOCKED",
            }
        market_finished = datetime.now(UTC)
        current_market = market_status(cutoff)
        provider_probes = provenance.get("provider_probes", {})
        provider_probes = provider_probes if isinstance(provider_probes, dict) else {}
        selected_lanes = sorted(
            {
                str(item.get("selection"))
                for item in provider_probes.values()
                if isinstance(item, dict) and item.get("selection")
            }
        )
        provider_status = "PASS" if quotes else "DATA_DEGRADED"
        if provenance.get("data_quality_mode") == "DATA_DEGRADED":
            provider_status = "DATA_DEGRADED"
        execution_mode = (
            "NORMAL"
            if current_market.status is MarketStatus.OPEN and bool(quotes)
            else "DEGRADED_OPERATIONAL"
            if current_market.status is MarketStatus.OPEN and bool(partial_quotes)
            else "SAFE_ANALYSIS"
        )
        startup.update(
            {
                "data_provider": {"status": provider_status, "selected_lanes": selected_lanes},
                "market_status": current_market.as_dict(),
                "execution_mode": execution_mode,
            }
        )
        closure = DailyClosureService(policies)
        parent_id = daily_run_id(account, quotes, cutoff, policies)
        settings = policies.models.research
        if settings is not None and research_live_enabled:
            # Paper runs opt in locally; the global models.yaml default stays unchanged.
            settings = settings.model_copy(
                update={"live_enabled": True, "timeout_seconds": min(settings.timeout_seconds, 30)}
            )

        def digest(value: object) -> str:
            return hashlib.sha256(
                json.dumps(value, sort_keys=True, default=str).encode()
            ).hexdigest()

        health = provenance.get("provider_health")
        health = health if isinstance(health, dict) else {}
        input_blockers = closure._gates(account, quotes, cutoff)
        market_valid = bool(quotes) and not any("MARKET" in reason for reason in input_blockers)
        research_inputs_ready = bool(research_quotes) and all(
            quote.timestamp <= cutoff
            and 0 <= (cutoff - quote.timestamp).total_seconds()
            <= policies.data.research.maximum_market_age_seconds
            for quote in research_quotes.values()
        )
        expected_closed_market = (
            current_market.status is not MarketStatus.OPEN
            and market_error is None
            and research_inputs_ready
        )
        host_job_path = os.environ.get("MERIDIAN_HOST_JOB")
        daily_data_status = (
            "PASS"
            if market_valid
            else "MARKET_CLOSED"
            if expected_closed_market
            else "FAILED"
        )

        def semantic_quote_payload(values: dict[str, MarketSnapshot]) -> dict[str, dict[str, object]]:
            return {
                ticker: {
                    key: value
                    for key, value in quote.model_dump(mode="json").items()
                    if key not in {"timestamp", "freshness_state"}
                }
                for ticker, quote in sorted(values.items())
            }

        host_resume_job = None
        host_result_invalidated = False
        if host_job_path:
            host_resume_job = load_job(Path(host_job_path))
            if host_resume_job.stage is not HostJobStage.RESEARCH:
                raise ValueError("HOST_LLM_RESULT_STALE")
            raw_job_quotes = host_resume_job.market_context.get("quotes", {})
            if not isinstance(raw_job_quotes, dict):
                raise ValueError("HOST_LLM_RESULT_STALE")
            try:
                frozen_quotes = {
                    str(ticker): MarketSnapshot.model_validate(value)
                    for ticker, value in raw_job_quotes.items()
                    if isinstance(ticker, str) and isinstance(value, dict)
                }
            except ValueError as error:
                raise ValueError("HOST_LLM_RESULT_STALE") from error
            if semantic_quote_payload(frozen_quotes) != semantic_quote_payload(research_quotes):
                old_run_id = host_resume_job.run_id
                from meridian.host_llm import HostLLMResult
                rebuilt_job, rebuilt_path = create_job(
                    self.paths,
                    run_id=parent_id,
                    stage=HostJobStage.RESEARCH,
                    market_context={
                        "cutoff": cutoff.isoformat(),
                        "quotes": {k: v.model_dump(mode="json") for k, v in research_quotes.items()},
                    },
                    portfolio_context={
                        "currency": account.currency,
                        "as_of": account.as_of.isoformat(),
                        "cash": str(account.cash),
                        "total_equity": str(account.total_equity),
                        "positions": [
                            {
                                "ticker": holding.ticker,
                                "market_value": str(holding.market_value),
                                "weight": str(
                                    holding.market_value / account.total_equity
                                    if account.total_equity
                                    else Decimal("0")
                                ),
                            }
                            for holding in account.holdings
                        ],
                        "account_identifier_included": False,
                    },
                    risk_context={"gates": list(input_blockers)},
                    strategy_context={
                        "mode": "PAPER_ONLY",
                        "execution_authority": "NONE",
                        "market_reference": digest(
                            {k: v.model_dump(mode="json") for k, v in research_quotes.items()}
                        ),
                    },
                    research_questions=("Assess the supplied current market evidence.",),
                    required_output_schema=HostLLMResult.model_json_schema(),
                )
                host_job_path = str(rebuilt_path)
                host_result_path = None
                host_result_invalidated = True
                host_resume_job = rebuilt_job
                startup["host_llm_recovery"] = {
                    "status": "REBUILT",
                    "reason": "HOST_LLM_RESULT_STALE",
                    "old_run_id": old_run_id,
                    "new_job_path": str(rebuilt_path),
                }
            else:
                # Resume uses the exact research snapshot from the job. A later
                # provider poll may update timestamps without changing decision facts.
                research_quotes = frozen_quotes

        eligible_research_tickers = tuple(
            ticker
            for ticker in sorted(research_quotes)
            if ticker in policies.universe.tickers and research_inputs_ready
        )
        universe_plan = (
            self.research_universe_scheduler.plan(
                eligible_research_tickers,
                research_quotes,
                policy=settings.budget,
                existing_holdings=tuple(holding.ticker for holding in account.holdings),
            )
            if settings is not None and eligible_research_tickers
            else None
        )
        research_request_tickers = (
            universe_plan.deep_analysis_universe
            if universe_plan is not None
            else eligible_research_tickers
        )
        total_equity = Decimal(account.total_equity)
        invested_value = sum(
            (Decimal(holding.market_value) for holding in account.holdings),
            Decimal("0"),
        )
        portfolio_context = {
            "currency": account.currency,
            "as_of": account.as_of.isoformat(),
            "cash": str(account.cash),
            "total_equity": str(account.total_equity),
            "cash_weight": str(
                Decimal(account.cash) / total_equity if total_equity else Decimal("0")
            ),
            "gross_exposure": str(invested_value / total_equity if total_equity else Decimal("0")),
            "positions": [
                {
                    "ticker": holding.ticker,
                    "market_value": str(holding.market_value),
                    "weight": str(
                        Decimal(holding.market_value) / total_equity
                        if total_equity
                        else Decimal("0")
                    ),
                }
                for holding in account.holdings
            ],
            "account_identifier_included": False,
            "persistence_allowed": False,
        }
        # Freeze the current account facts before any model invocation. The
        # resulting value is read-only and remains excluded from persisted
        # research request hashes by DailyResearchInput.
        portfolio_context = PortfolioSnapshot.from_account_snapshot(account).research_view()
        request = DailyResearchInput(
            parent_run_id=parent_id,
            analysis_cutoff=cutoff,
            mode="FIXTURE" if market_fixture or snapshot.source_kind == "FIXTURE" else "LIVE",
            snapshot_reference=snapshot.content_hash or "UNAVAILABLE",
            market_reference=digest(
                {symbol: quote.model_dump(mode="json") for symbol, quote in research_quotes.items()}
            ),
            temporal_context=ResearchTemporalContext(
                run_id=parent_id,
                trading_date=cutoff.astimezone(ZoneInfo("America/New_York")).date(),
                as_of=cutoff,
                information_cutoff=cutoff,
                market_session=current_market.status.value,
                timezone="America/New_York",
                portfolio_snapshot_id=account.snapshot_id,
            ),
            policy_reference=digest(
                {name: value.model_dump(mode="json") for name, value in vars(policies).items()}
            ),
            provider=settings.provider if settings else "UNCONFIGURED",
            model=settings.model if settings else "UNCONFIGURED",
            observations=tuple(
                PublicResearchObservation(
                    ticker=ticker,
                    observed_at=research_quotes[ticker].timestamp,
                    price=research_quotes[ticker].last,
                    daily_return=research_quotes[ticker].daily_return,
                    reference=digest(research_quotes[ticker].model_dump(mode="json")),
                )
                for ticker in research_request_tickers
            ),
            freshness_status="PASS" if research_inputs_ready else "BLOCKED",
            provider_provenance={
                ticker: json.dumps(health, sort_keys=True) for ticker, health in health.items()
            },
            universe_plan=universe_plan,
            portfolio_context=portfolio_context,
        )
        host_mode = os.environ.get("MERIDIAN_LLM_MODE", "").upper() == "HOST_CODEX"
        if not host_result_invalidated:
            host_job_path = os.environ.get("MERIDIAN_HOST_JOB")
            host_result_path = os.environ.get("MERIDIAN_HOST_RESULT")
        host_research: ResearchStageResult | None = None
        if host_mode:
            from meridian.host_llm import HostLLMResult
            evidence_ids = {item.ticker: item.reference for item in request.observations}
            if host_job_path:
                job_path = Path(host_job_path)
                job = host_resume_job or load_job(job_path)
                if job.stage is not HostJobStage.RESEARCH or job.strategy_context.get("market_reference") != request.market_reference:
                    raise ValueError("HOST_LLM_RESULT_STALE")
            else:
                job, job_path = create_job(self.paths, run_id=parent_id, stage=HostJobStage.RESEARCH,
                    market_context={"cutoff": cutoff.isoformat(), "quotes": {k: v.model_dump(mode="json") for k, v in research_quotes.items()}, "evidence_ids": evidence_ids},
                    portfolio_context=portfolio_context, risk_context={"gates": list(input_blockers)},
                    strategy_context={"mode": "PAPER_ONLY", "execution_authority": "NONE", "market_reference": request.market_reference, "input_hash": request.input_hash},
                    research_questions=("Assess the supplied current market evidence.",),
                    required_output_schema=HostLLMResult.model_json_schema())
            if not host_result_path:
                host_research = ResearchStageResult(
                    context=ResearchDecisionContext(research_run_id="host-" + parent_id, parent_run_id=parent_id,
                        input_hash=request.input_hash, analysis_cutoff=cutoff, status=ResearchProviderStatus.NOT_RUN),
                    prompt_created_at=cutoff, started_at=cutoff, finished_at=cutoff, duration_seconds=0, attempts=0,
                    provider="HOST_CODEX", model="HOST", error_code="HOST_LLM_REQUIRED",
                    next_action=f"Codex host must read {job_path} and write a validated result JSON; rerun with MERIDIAN_HOST_RESULT.",
                    preparation_diagnostics={"execution_mode": "HOST_CODEX", "job_path": str(job_path), "result_path": None})
            else:
                try:
                    job_loaded = load_job(job_path)
                    host_result, accepted_path = accept_result(job_loaded, Path(host_result_path))
                    expected_refs = {item.reference for item in request.observations}
                    if not expected_refs <= set(host_result.evidence):
                        raise ValueError("HOST_LLM_RESULT_INVALID")
                    regime = host_result.market_regime.upper()
                    direction = "BULLISH" if "BULL" in regime else "BEARISH" if "BEAR" in regime else "NEUTRAL"
                    output = DailyResearchOutput(results=tuple(SymbolResearch(ticker=item.ticker,
                        claim_kind="MODEL_INFERENCE", direction=direction,
                        research_conviction=Decimal(str(host_result.confidence)), thesis=host_result.summary,
                        risks=host_result.risks, cited_evidence_ids=(item.reference,),
                        data_limitations=host_result.uncertainties or ("HOST_RESULT_LIMITATIONS_UNSPECIFIED",))
                        for item in request.observations))
                    output.validate_input(request)
                    host_research = ResearchStageResult(
                        context=ResearchDecisionContext(research_run_id="host-" + parent_id, parent_run_id=parent_id,
                            input_hash=request.input_hash, analysis_cutoff=cutoff, status=ResearchProviderStatus.AVAILABLE,
                            output=output), prompt_created_at=cutoff, started_at=cutoff, finished_at=datetime.now(UTC),
                        duration_seconds=0, attempts=1, provider="HOST_CODEX", model="CHATGPT_HOST", provenance="REPLAY",
                        response_received_at=datetime.now(UTC), error_code=None,
                        next_action="Host result validated; deterministic portfolio and paper gates remain authoritative.",
                        preparation_diagnostics={"execution_mode": "HOST_CODEX", "job_path": str(job_path), "result_path": str(accepted_path)})
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    host_research = ResearchStageResult(
                        context=ResearchDecisionContext(research_run_id="host-" + parent_id, parent_run_id=parent_id,
                            input_hash=request.input_hash, analysis_cutoff=cutoff, status=ResearchProviderStatus.INVALID_RESPONSE),
                        prompt_created_at=cutoff, started_at=cutoff, finished_at=datetime.now(UTC), duration_seconds=0,
                        attempts=1, provider="HOST_CODEX", model="CHATGPT_HOST", error_code="HOST_LLM_RESULT_INVALID",
                        next_action="Fix the host result JSON and rerun resume.",
                        preparation_diagnostics={"execution_mode": "HOST_CODEX", "job_path": str(job_path), "result_path": host_result_path, "error_type": type(error).__name__})
        logger.info("run_id=%s stage=research start", parent_id)
        native_result = None
        use_native = (
            settings is not None
            and settings.research_engine == "gpt_native_v1"
            and request.mode == "LIVE"
            and not bool(getattr(self.research_stage.provider, "_injected_runner", False))
            and not host_mode
        )
        if use_native:
            assert settings is not None
            execution_data_status = (
                "PASS"
                if market_valid
                and all(
                    0 <= (cutoff - quote.timestamp).total_seconds()
                    <= policies.data.execution.maximum_quote_age_seconds
                    for quote in quotes.values()
                )
                else "BLOCKED"
            )
            native_execution_state = (
                ExecutionState.BLOCKED_MARKET_CLOSED
                if current_market.status is not MarketStatus.OPEN
                else ExecutionState.BLOCKED_DATA_QUALITY
                if not market_valid
                else ExecutionState.BLOCKED_POLICY
            )
            native_result = self.native_research.run(
                request,
                research_data_status="PASS" if research_inputs_ready else "BLOCKED",
                execution_data_status=execution_data_status,
                execution_state=native_execution_state,
                settings=settings,
                run_id=parent_id,
            )
            now = datetime.now(UTC)
            native_status = (
                ResearchProviderStatus.CODEX_TIMEOUT
                if any(
                    stage.status.value == "TIMEOUT"
                    for stage in native_result.stages.values()
                )
                else ResearchProviderStatus.CODEX_PROCESS_ERROR
                if any(
                    stage.status.value in {"PROCESS_ERROR", "AUTH_ERROR", "NOT_AVAILABLE"}
                    for stage in native_result.stages.values()
                )
                else ResearchProviderStatus.INVALID_RESPONSE
            )
            research = ResearchStageResult(
                context=ResearchDecisionContext(
                    research_run_id="native-" + parent_id,
                    parent_run_id=parent_id,
                    input_hash=request.input_hash,
                    analysis_cutoff=cutoff,
                    status=native_status,
                ),
                prompt_created_at=now,
                started_at=now,
                finished_at=now,
                duration_seconds=0,
                attempts=0,
                provider="GPT_NATIVE_V1",
                model=settings.model,
                error_code=None,
                next_action="Research remains advisory; deterministic execution gates remain authoritative.",
            )
            research_mode = native_result.research_state.value
            research_degradation = {
                "research_mode": research_mode,
                "research_confidence": native_result.confidence.system_confidence,
                "llm_available": any(
                    stage.status.value == "SUCCESS" for stage in native_result.stages.values()
                ),
                "fallback_reason": ",".join(native_result.degradation_reasons) or None,
                "evidence_synthesis": "GPT_NATIVE_EVIDENCE_FIRST",
            }
        elif host_mode and host_research is not None:
            research = host_research
            research_mode = "FULL_RESEARCH" if research.context.status is ResearchProviderStatus.AVAILABLE else "HOST_LLM_REQUIRED"
            research_degradation = {"research_mode": research_mode, "research_confidence": "HOST_VALIDATED" if research.context.status is ResearchProviderStatus.AVAILABLE else "NONE", "llm_available": research.context.status is ResearchProviderStatus.AVAILABLE, "fallback_reason": research.error_code, "evidence_synthesis": "HOST_CODEX"}
        else:
            research = self.research_stage.run(request, settings)
            research_mode = (
                "FULL_RESEARCH"
                if research.context.status is ResearchProviderStatus.AVAILABLE
                else "DEGRADED_RESEARCH"
                if research.error_code == "CODEX_RATE_LIMITED"
                else "OFFLINE_RESEARCH"
            )
            research_degradation = {
                "research_mode": research_mode,
                "research_confidence": "NORMAL"
                if research_mode == "FULL_RESEARCH"
                else "LOW"
                if research_mode == "DEGRADED_RESEARCH"
                else "NONE",
                "llm_available": research_mode == "FULL_RESEARCH",
                "fallback_reason": None
                if research_mode == "FULL_RESEARCH"
                else research.error_code or "RESEARCH_UNAVAILABLE",
                "evidence_synthesis": "CODEX"
                if research_mode == "FULL_RESEARCH"
                else "DETERMINISTIC_STRUCTURED_INPUTS_ONLY",
            }
        logger.info(
            "run_id=%s stage=research status=%s duration=%s code=%s",
            parent_id,
            native_result.research_state.value if native_result else research.context.status.value,
            research.duration_seconds,
            research.error_code,
        )
        evaluated_at = datetime.now(UTC)
        result = closure.run(
            account, quotes, cutoff=cutoff, research=research.context, evaluated_at=evaluated_at
        )
        if (
            native_result is not None
            and native_result.execution_state is not ExecutionState.READY
            and result.decision.overall_status is RunStatus.DRAFT
        ):
            # GPT-native research has no execution authority.  Preserve the
            # deterministic target for analysis, but never emit an order draft
            # when its independent execution gate is blocked.
            decision = result.decision.model_copy(
                update={"orders": (), "overall_status": RunStatus.NO_ACTION}
            )
            result = DailyClosureResult(
                decision=decision,
                report={**result.report, "orders": [], "status": RunStatus.NO_ACTION.value},
            )
        result.report.update(
            {
                "research": {**research.model_dump(mode="json"), **research_degradation},
                "research_intelligence": (
                    native_result.model_dump(mode="json") if native_result is not None else None
                ),
                "research_input": request.model_dump(mode="json"),
                "data_auto_retrieval": research.preparation_diagnostics,
                "research_universe": universe_plan.model_dump(mode="json")
                if universe_plan
                else {
                    "eligible_universe": [],
                    "research_universe": [],
                    "deep_analysis_universe": [],
                    "original_count": 0,
                    "research_count": 0,
                    "deep_analysis_count": 0,
                    "mode": "full",
                    "selection_basis": "FULL_UNIVERSE",
                },
                "stages": [
                    {
                        "stage": "market",
                        "run_id": parent_id,
                        "start": market_started.isoformat(),
                        "finish": market_finished.isoformat(),
                        "duration_seconds": (market_finished - market_started).total_seconds(),
                        "status": daily_data_status,
                        "error_code": market_error
                        or (
                            None
                            if market_valid or expected_closed_market
                            else "MARKET_INPUT_NOT_READY"
                        ),
                        "next_action": (
                            "Wait for the next regular session; completed-session data remains research-only."
                            if expected_closed_market
                            else "Review provider probes and freshness."
                        ),
                    },
                    {
                        "stage": "research",
                        "run_id": parent_id,
                        "start": research.started_at.isoformat(),
                        "finish": research.finished_at.isoformat(),
                        "duration_seconds": research.duration_seconds,
                        "status": research.context.status.value,
                        "error_code": research.error_code,
                        "next_action": research.next_action,
                    },
                    {
                        "stage": "decision",
                        "run_id": parent_id,
                        "start": evaluated_at.isoformat(),
                        "finish": datetime.now(UTC).isoformat(),
                        "duration_seconds": (datetime.now(UTC) - evaluated_at).total_seconds(),
                        "status": result.decision.overall_status.value,
                        "error_code": None,
                        "next_action": "Review deterministic policy gates; no manual authority inferred.",
                    },
                ],
            }
        )
        result.report.update(provenance)
        if native_result is not None:
            try:
                result.report["research_trace_json"] = str(
                    persist_research_trace(native_result, self.paths, cutoff)
                )
            except OSError:
                result.report["research_trace_error"] = "RESEARCH_TRACE_PERSISTENCE_FAILED"
        result.report["research_audit_files"] = write_research_audit(
            self.paths.logs / "research",
            parent_id,
            research=research.model_dump(mode="json"),
            decision=result.decision.model_dump(mode="json"),
        )
        # Reuse the selected canonical public observations for any downstream
        # paper-only fill simulation; paper code never performs a shadow fetch.
        market_observations: dict[str, dict[str, object]] = {}
        raw_probes = provenance.get("provider_probes", {})
        raw_probes = raw_probes if isinstance(raw_probes, dict) else {}
        for ticker, quote in quotes.items():
            probe = raw_probes.get(ticker, {})
            probe = probe if isinstance(probe, dict) else {}
            market_observations[ticker] = {
                "last": str(quote.last),
                "timestamp": quote.timestamp.isoformat(),
                "freshness_state": quote.freshness_state.value,
                "provider": probe.get("selected_provider") or "PUBLIC_PROVIDER",
                "quote_kind": "PUBLIC_RESEARCH_QUOTE",
            }
        result.report["market_observations"] = market_observations
        if market_error:
            result.report.update(
                {"error_code": market_error, "exit_code": 3, "error_category": "DATA_QUALITY"}
            )
        analysis_ok = result.report["status"] in {"DRAFT", "NO_ACTION", "NO_CAPITAL"}
        directory = (
            self.paths.reports / result.decision.as_of.date().isoformat() / result.decision.run_id
        )
        total_equity = account.total_equity
        invested_value = sum((holding.market_value for holding in account.holdings), Decimal("0"))
        position_weights = (
            [holding.market_value / total_equity for holding in account.holdings]
            if total_equity > 0
            else []
        )
        safe_analysis = {
            "status": "NOT_REQUIRED" if market_valid else "COMPLETED_NO_EXECUTION",
            "risk_analysis": {
                "status": "PASS_ACCOUNT_ONLY",
                "cash": str(account.cash),
                "total_equity": str(total_equity),
                "gross_exposure": str(
                    invested_value / total_equity if total_equity > 0 else Decimal("0")
                ),
                "max_position_weight": str(max(position_weights, default=Decimal("0"))),
                "limitations": [
                    "No fresh complete market snapshot; price-sensitive risk is not asserted"
                ]
                if not market_valid
                else [],
            },
            "portfolio_check": {
                "status": "PASS_ACCOUNT_FACTS_ONLY",
                "position_count": len(account.holdings),
                "negative_cash": account.cash < 0,
                "long_only": all(holding.quantity >= 0 for holding in account.holdings),
            },
            "historical_factor_analysis": {
                "status": "PARTIAL" if partial_quotes else "NOT_RUN",
                "symbols": sorted(partial_quotes),
                "reason": "Only verified operational observations already produced by the canonical market stage are shown; no missing factor is fabricated.",
            },
            "simulated_decision": {
                "status": "BLOCKED" if not market_valid else "NOT_REQUIRED",
                "action": "HOLD" if not market_valid else None,
                "orders": [],
                "authority": "NONE",
                "reason": "Fresh complete market data is required before deterministic order construction."
                if not market_valid
                else None,
            },
        }
        preflight_cache = preflight.get("cache", {})
        cache_degraded = (
            isinstance(preflight_cache, dict) and preflight_cache.get("status") != "READY"
        )
        result.report.update(
            {
                "timestamp": cutoff.isoformat(),
                "trading_date": cutoff.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
                "runtime_status": "PASS" if preflight["status"] != "FAIL" else "FAILED",
                "database_status": "PASS",
                "startup_diagnostics": startup,
                "market_status": current_market.as_dict(),
                "execution_mode": execution_mode,
                "data_quality_mode": provenance.get("data_quality_mode", "NORMAL"),
                "safe_analysis": safe_analysis,
                "data_status": daily_data_status,
                "market_data_tradeable": (
                    current_market.status is MarketStatus.OPEN and market_valid
                ),
                "portfolio_status": account.freshness_state.value,
                "research_status": research.context.status.value,
                "quant_status": "PASS"
                if result.decision.target_portfolio is not None
                else "NOT_RUN",
                "risk_status": "PASS"
                if result.decision.target_portfolio is not None and analysis_ok
                else "NOT_RUN",
                "recommendation_status": "RESEARCH_ONLY" if analysis_ok else "BLOCKED",
                "warnings": [
                    "PUBLIC_RESEARCH_IS_ADVISORY_NOT_CERTIFIED",
                    "NOT_AUTHORIZED_FOR_MANUAL_ENTRY",
                ]
                + (["CACHE_DEGRADED"] if cache_degraded else [])
                + (
                    ["DATA_DEGRADED"]
                    if provenance.get("data_quality_mode") == "DATA_DEGRADED"
                    else []
                ),
                "errors": list(result.decision.blocked_reasons)
                + ([market_error] if market_error else []),
                "output_files": {
                    "report_json": str(directory / "daily.json"),
                    "report_markdown": str(directory / "daily.md"),
                    "log": str(log_path),
                },
                "elapsed_seconds": round(monotonic() - started, 3),
            }
        )
        market_ok = result.report["data_status"] == "PASS"
        snapshot_fresh = (
            evaluated_at - account.as_of
        ).total_seconds() <= policies.data.account_snapshot_max_age_seconds
        research_available = (native_result is not None and native_result.research_state.value in {"RESEARCH_READY", "RESEARCH_DEGRADED"}) or research.context.status is ResearchProviderStatus.AVAILABLE
        research_health = (
            ReadinessStatus.PASS
            if research_available
            else ReadinessStatus.NOT_RUN
            if research.context.status is ResearchProviderStatus.NOT_RUN
            else ReadinessStatus.BLOCKED
        )
        ready = RecommendationReadiness(
            research_status=research_health,
            research_freshness=ReadinessStatus.PASS
            if research_available
            and research.response_received_at is not None
            and 0
            <= (evaluated_at - research.response_received_at).total_seconds()
            <= (settings.live_as_of_tolerance_seconds if settings else 0)
            else ReadinessStatus.UNKNOWN,
            runtime_health=ReadinessStatus(str(preflight["status"])),
            account_snapshot_status=snapshot.status,
            account_snapshot_freshness=ReadinessStatus.PASS
            if snapshot_fresh
            else ReadinessStatus.BLOCKED,
            account_provenance=snapshot.provenance_status,
            market_data_status=ReadinessStatus.PASS if quotes else ReadinessStatus.BLOCKED,
            market_data_freshness=ReadinessStatus.PASS if market_ok else ReadinessStatus.BLOCKED,
            provider_provenance=ReadinessStatus.DEGRADED
            if market_fixture
            else ReadinessStatus.PASS
            if provenance.get("provider_probes")
            else ReadinessStatus.UNKNOWN,
            decision_pipeline_status=ReadinessStatus.PASS
            if result.decision.target_portfolio is not None and analysis_ok
            else ReadinessStatus.FAILED
            if result.report["status"] == "FAILED"
            else ReadinessStatus.NOT_RUN,
            policy_gate_status=ReadinessStatus.DEGRADED
            if result.decision.target_portfolio is not None
            else ReadinessStatus.NOT_RUN,
            quote_certification_status=ReadinessStatus.BLOCKED,
            input_mode=(
                "FIXTURE"
                if market_fixture or snapshot.source_kind == "FIXTURE"
                else "PAPER_LEDGER"
                if snapshot.source_kind == "PAPER_LEDGER"
                else "HOST_SUPPLIED_UNVERIFIED"
            ),
            quote_kind="PUBLIC_RESEARCH_QUOTE" if not market_fixture else "FIXTURE",
        )
        reconciliation = result.report.get("reconciliation")
        reconciled = isinstance(reconciliation, dict) and reconciliation.get("status") == "DRAFT"
        gate_specs = (
            (
                "ACCOUNT_READY",
                ReadinessStatus.PASS
                if ready.account_provenance is ReadinessStatus.PASS and snapshot_fresh
                else ReadinessStatus.BLOCKED,
                "Fresh authoritative paper ledger observation"
                if snapshot.source_kind == "PAPER_LEDGER"
                else "Authenticated fresh Host source required",
                snapshot.content_hash or "UNAVAILABLE",
            ),
            (
                "SECURITY_READY",
                ready.policy_gate_status,
                "Operational sector metadata is not authoritative certification",
                request.policy_reference,
            ),
            (
                "MARKET_READY",
                ready.market_data_freshness,
                "Market observations must be fresh at decision time",
                request.market_reference,
            ),
            (
                "RESEARCH_READY",
                ReadinessStatus.DEGRADED if research_available else research_health,
                "Public model inference is advisory, not certified evidence",
                research.context.input_hash,
            ),
            (
                "QUOTE_READY",
                ready.quote_certification_status,
                "Certified execution quote absent",
                "UNAVAILABLE",
            ),
            (
                "RISK_READY",
                ReadinessStatus.PASS
                if result.report["risk_status"] == "PASS"
                else ReadinessStatus.BLOCKED,
                "Deterministic projected portfolio validation",
                request.policy_reference,
            ),
            (
                "RECONCILIATION_READY",
                ReadinessStatus.PASS if reconciled and snapshot_fresh else ReadinessStatus.BLOCKED,
                "Reconciliation uses supplied facts; no fills inferred",
                snapshot.content_hash or "UNAVAILABLE",
            ),
        )
        gates = tuple(
            ReadinessGateResult(gate=name, status=status, reason=reason, evidence=(reference,))
            for name, status, reason, reference in gate_specs
        )
        result.report.update(
            {
                "gates": [gate.model_dump(mode="json") for gate in gates],
                "manual_authority": {
                    "status": "BLOCKED"
                    if any(gate.status is not ReadinessStatus.PASS for gate in gates)
                    else "MANUAL_REVIEW_REQUIRED",
                    "certificate_issued": False,
                    "reason": "Existing sealed authority and certified quote remain required.",
                },
                "readiness": ready.model_dump(mode="json"),
                "snapshot_provenance": snapshot.model_dump(mode="json"),
                "next_actions": [
                    "Provide verifiable authorized Host source evidence; content hashes are not authentication.",
                    "Supply fresh market observations if freshness is blocked.",
                    "Run certified research and policy gates before recommendation readiness.",
                    "Manual entry additionally requires a certified execution quote and sealed authority.",
                ],
                "degraded_reasons": [
                    "RESEARCH_ADVISORY_ONLY"
                    if research_available
                    else "RESEARCH_" + research.context.status.value,
                    "POLICY_SECURITY_METADATA_UNCERTIFIED",
                    "PUBLIC_QUOTE_UNCERTIFIED",
                ],
            }
        )
        # Forward evidence consumes this exact final decision and the already-selected
        # operational observations. It is intentionally observational: it never
        # recalculates an order, upgrades public data, or promotes a strategy.
        forward_policy = load_forward_evidence_policy(policy_directory())
        forward_ledger = ForwardLedger(self.paths.audit / "forward-evidence.json")
        forward_freeze: dict[str, object]
        forward_outcomes: dict[str, object]
        try:
            if analysis_ok and market_ok:
                targets = result.decision.target_portfolio
                target_weights = (
                    {item.ticker: item.target_weight for item in targets.positions}
                    if targets is not None
                    else {}
                )
                order_signals = {item.ticker: item.side.value for item in result.decision.orders}
                quote_prices = {ticker: quote.last for ticker, quote in quotes.items()}
                forward_freeze = freeze_canonical_predictions(
                    forward_ledger,
                    policy=forward_policy,
                    decision_run_id=result.decision.run_id,
                    decision_timestamp=result.decision.as_of,
                    information_cutoff=cutoff,
                    account_reference=digest(account.account_alias),
                    universe=tuple(sorted(policies.universe.tickers)),
                    prices=quote_prices,
                    quant_scores={ticker: quote.daily_return for ticker, quote in quotes.items()},
                    target_weights=target_weights,
                    order_signals=order_signals,
                    cash_weight=targets.cash_weight if targets is not None else Decimal("1"),
                    market_snapshot_hash=str(result.report["market_data_snapshot_hash"]),
                    policy_digest=forward_policy_hash(forward_policy),
                    model_config_digest=digest(policies.models.model_dump(mode="json")),
                    research_available=research_available,
                    data_mode=str(provenance["data_mode"]),
                )
                forward_outcomes = forward_ledger.ingest_prices(
                    observed_at=cutoff,
                    prices=quote_prices,
                    source="CANONICAL_OPERATIONAL_MARKET_SNAPSHOT",
                )
            else:
                forward_freeze = {
                    "status": "FORWARD_NOT_FROZEN",
                    "reason": "CANONICAL_DECISION_OR_MARKET_NOT_READY",
                }
                forward_outcomes = {
                    "status": "FORWARD_OUTCOME_NOT_READY",
                    "reason": "CANONICAL_MARKET_NOT_READY",
                }
            forward_summary = forward_ledger.evaluate(
                minimum_samples=forward_policy.minimum_mature_samples
            )
            result.report["forward_evidence"] = {
                "status": forward_summary["status"],
                "freeze": forward_freeze,
                "outcomes": forward_outcomes,
                "summary": forward_summary,
                "policy_hash": forward_policy_hash(forward_policy),
                "authority": "SHADOW_EVIDENCE_ONLY_NO_AUTOMATIC_PROMOTION",
            }
        except (OSError, ValueError):
            result.report["forward_evidence"] = {
                "status": "BLOCKED",
                "freeze": {"status": "FORWARD_NOT_FROZEN"},
                "outcomes": {"status": "FORWARD_OUTCOME_NOT_READY"},
                "summary": {"status": "BLOCKED"},
                "authority": "SHADOW_EVIDENCE_ONLY_NO_AUTOMATIC_PROMOTION",
                "error_code": "FORWARD_EVIDENCE_INTEGRITY_OR_STORAGE_FAILED",
            }
            errors = result.report.get("errors", [])
            next_actions = result.report.get("next_actions", [])
            result.report["errors"] = (
                [*errors, "FORWARD_EVIDENCE_INTEGRITY_OR_STORAGE_FAILED"]
                if isinstance(errors, list)
                else ["FORWARD_EVIDENCE_INTEGRITY_OR_STORAGE_FAILED"]
            )
            result.report["next_actions"] = (
                [
                    *next_actions,
                    "Inspect forward evidence storage and preserve the conflicting receipt; do not infer a replacement prediction.",
                ]
                if isinstance(next_actions, list)
                else [
                    "Inspect forward evidence storage and preserve the conflicting receipt; do not infer a replacement prediction."
                ]
            )
        AuditStore(self.paths.db).write_decision(result.decision)
        AuditStore(self.paths.db).write_readiness(
            result.decision.run_id,
            cutoff.isoformat(),
            str(result.report["status"]),
            {
                "research": result.report["research"],
                "research_input": result.report["research_input"],
                "decision_context": result.report["decision_context"],
                "gates": result.report["gates"],
                "stages": result.report["stages"],
                "manual_authority": result.report["manual_authority"],
                "readiness": result.report["readiness"],
                "snapshot_provenance": result.report["snapshot_provenance"],
                "provider_probes": provenance.get("provider_probes", {}),
                "data_mode": provenance["data_mode"],
                "next_actions": result.report["next_actions"],
                "errors": result.report["errors"],
                "error_code": result.report.get("error_code"),
            },
        )
        logger.info(
            "run_id=%s data_mode=%s elapsed_seconds=%s",
            result.decision.run_id,
            provenance["data_mode"],
            result.report["elapsed_seconds"],
        )
        logger.info(
            "recommendation=%s blockers=%s", ready.recommendation_readiness.value, ready.blockers
        )
        logger.warning(
            "Research status=%s; advisory-only, no manual-entry authority",
            research.context.status.value,
        )
        logger.info(
            "status=%s provider_health=%s report=%s",
            result.report["status"],
            provenance["provider_health"],
            directory,
        )
        return self._complete_report(result.report)

    def _complete_report(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            json_path, markdown_path = persist_run_report(payload, self.paths)
            result = {
                **payload,
                "report_json": str(json_path),
                "report_markdown": str(markdown_path),
            }
            try:
                result["run_health_json"] = str(persist_run_health(result, self.paths))
            except OSError as error:
                logging.getLogger("meridian.run_health").error(
                    "RUN_HEALTH_PERSISTENCE_FAILED error_type=%s", type(error).__name__
                )
                result["run_health_error"] = "RUN_HEALTH_PERSISTENCE_FAILED"
            return result
        except OSError:
            # Analysis may already be durable. Keep its identity and append a failure
            # receipt rather than replacing immutable evidence or inventing a new run.
            outputs = payload.get("output_files", {})
            outputs = outputs if isinstance(outputs, dict) else {}
            raw_readiness = payload.get("readiness", {})
            raw_readiness = raw_readiness if isinstance(raw_readiness, dict) else {}
            readiness = RecommendationReadiness.model_validate(
                {
                    key: value
                    for key, value in raw_readiness.items()
                    if key in RecommendationReadiness.model_fields
                }
            ).model_copy(update={"runtime_health": ReadinessStatus.FAILED})
            failure = {
                **payload,
                "status": "FAILED",
                "runtime_status": "FAILED",
                "exit_code": 3,
                "error_code": "MERIDIAN_REPORT_WRITE_FAILED",
                "error_category": "USER_FIXABLE",
                "recommendation_status": "BLOCKED",
                "report_persistence_status": "FAILED",
                "readiness": readiness.model_dump(mode="json"),
                "errors": ["MERIDIAN_REPORT_WRITE_FAILED"],
                "next_actions": [
                    "Check report directory permissions, free space and file locks. Partial files are not a completed report; preserve audit history and use this run_id for diagnosis."
                ],
                "partial_output_files": {
                    key: value
                    for key, value in outputs.items()
                    if key != "log" and Path(str(value)).is_file()
                },
                "output_files": {
                    key: value
                    for key, value in outputs.items()
                    if key == "log" and Path(str(value)).is_file()
                },
                "audit_failure_recorded": True,
            }
            try:
                AuditStore(self.paths.db).write_readiness(
                    str(payload["run_id"]) + ":report-failure",
                    str(payload["analysis_time"]),
                    "FAILED",
                    {
                        "event_type": "REPORT_PERSISTENCE_FAILED",
                        "parent_run_id": payload["run_id"],
                        "error_code": failure["error_code"],
                        "runtime_status": "FAILED",
                    },
                )
            except (OSError, sqlite3.Error):
                failure["audit_failure_recorded"] = False
            return failure

    def _paper_ledger(self) -> PaperLedger:
        return PaperLedger(
            AuditStore(self.paths.db), PaperSettings.from_policy_directory(policy_directory())
        )

    def paper_init(
        self,
        account_name: str = DEFAULT_ACCOUNT,
        *,
        cash: Decimal = DEFAULT_INITIAL_CASH,
        currency: str = "USD",
    ) -> dict[str, object]:
        initialized = self.init()
        if initialized["status"] == "INIT_FAILED":
            return initialized
        account, created = self._paper_ledger().initialize(
            account_name, cash=cash, currency=currency
        )
        payload = self._paper_ledger().status(account_name)
        payload.update(
            {
                "status": "PAPER_INITIALIZED" if created else "PAPER_ACCOUNT_ALREADY_EXISTS",
                "created": created,
                "reset_performed": False,
                "next_actions": (
                    ["Run `meridian paper run --account Schwab-Paper --json`."]
                    if created
                    else ["Account was preserved; ordinary paper runs never reset history."]
                ),
            }
        )
        return payload

    def paper_status(self, account_name: str = DEFAULT_ACCOUNT) -> dict[str, object]:
        return self._paper_ledger().status(account_name)

    def paper_history(self, account_name: str = DEFAULT_ACCOUNT) -> dict[str, object]:
        return {
            "status": "PAPER_HISTORY",
            "account": account_name,
            "history": self._paper_ledger().history(account_name),
        }

    def paper_trades(self, account_name: str = DEFAULT_ACCOUNT) -> dict[str, object]:
        return {
            "status": "PAPER_TRADES",
            "account": account_name,
            "trades": self._paper_ledger().trades(account_name),
        }

    def paper_reset(self, account_name: str, *, confirmation: str | None) -> dict[str, object]:
        if confirmation != account_name:
            raise ValueError("PAPER_RESET_CONFIRMATION_REQUIRED")
        self._paper_ledger().reset(account_name, confirmation=account_name)
        return {
            "status": "PAPER_RESET_COMPLETE",
            "account": account_name,
            "reset_performed": True,
            "next_actions": [
                "The account is empty. Run `paper init` explicitly to create a new paper account."
            ],
        }

    @staticmethod
    def _paper_quotes(daily: dict[str, object]) -> dict[str, dict[str, object]]:
        raw = daily.get("market_observations", {})
        if not isinstance(raw, dict):
            return {}
        quotes: dict[str, dict[str, object]] = {}
        for ticker, item in raw.items():
            if isinstance(ticker, str) and isinstance(item, dict):
                quotes[ticker] = dict(item)
        return quotes

    def _persist_paper_report(self, payload: dict[str, object]) -> dict[str, str]:
        analysis = datetime.fromisoformat(str(payload["analysis_time"]))
        run_id = str(payload["paper_run_id"])
        directory = self.paths.reports / analysis.date().isoformat() / run_id
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / "paper-daily.json"
        markdown_path = directory / "paper-daily.md"
        temporary = json_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        publish_staged_report(temporary, json_path)
        portfolio = payload.get("portfolio", {})
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        performance = payload.get("performance", {})
        performance = performance if isinstance(performance, dict) else {}
        execution = payload.get("paper_execution", {})
        execution = execution if isinstance(execution, dict) else {}
        research = payload.get("research", {})
        research = research if isinstance(research, dict) else {}
        research_context = research.get("context", {})
        research_context = research_context if isinstance(research_context, dict) else {}
        research_diagnostics = research.get("provider_diagnostics", {})
        research_diagnostics = (
            research_diagnostics if isinstance(research_diagnostics, dict) else {}
        )
        research_response = research.get("structured_response", {})
        research_response = research_response if isinstance(research_response, dict) else {}
        research_universe = payload.get("research_universe", {})
        research_universe = research_universe if isinstance(research_universe, dict) else {}
        retrieval = payload.get("data_auto_retrieval", {})
        retrieval = retrieval if isinstance(retrieval, dict) else {}
        forward = payload.get("forward_evidence", {})
        forward = forward if isinstance(forward, dict) else {}
        market = payload.get("market", {})
        market = market if isinstance(market, dict) else {}
        decision = payload.get("decision", {})
        decision = decision if isinstance(decision, dict) else {}
        startup = payload.get("startup_diagnostics", {})
        startup = startup if isinstance(startup, dict) else {}
        environment = startup.get("environment", {})
        environment = environment if isinstance(environment, dict) else {}
        cache = startup.get("cache", {})
        cache = cache if isinstance(cache, dict) else {}
        provider = startup.get("data_provider", {})
        provider = provider if isinstance(provider, dict) else {}
        market_status_summary = startup.get("market_status", {})
        market_status_summary = (
            market_status_summary if isinstance(market_status_summary, dict) else {}
        )
        evidence_catalog = retrieval.get("evidence_catalog", [])
        lines = [
            "# Meridian Daily — Schwab-Paper",
            "",
            f"Status: **{payload.get('status', 'UNKNOWN')}**",
            f"Canonical run: `{payload.get('canonical_run_id', 'UNKNOWN')}`",
            f"Environment: **{environment.get('status', payload.get('runtime_status', 'UNKNOWN'))}**",
            f"Cache: **{cache.get('status', 'UNKNOWN')}** ({cache.get('error_code') or 'healthy'})",
            f"Data Provider: **{provider.get('status', 'NOT_RUN')}**; lanes: {', '.join(provider.get('selected_lanes', [])) or 'NONE'}",
            f"Market Status: **{market_status_summary.get('status', market.get('session', 'UNKNOWN'))}**",
            f"Execution Mode: **{payload.get('execution_mode', 'SAFE_ANALYSIS')}**",
            f"Research Universe: **{research_universe.get('mode', 'full')}**; "
            f"eligible {research_universe.get('original_count', 0)} -> "
            f"research {research_universe.get('research_count', 0)} -> "
            f"deep analysis {research_universe.get('deep_analysis_count', 0)}",
            "",
            "## Data auto-retrieval",
            "",
            f"Initial completeness: **{retrieval.get('initial_completeness', 'NOT_RUN')}**",
            f"Final completeness: **{retrieval.get('final_completeness', 'NOT_RUN')}**",
            f"Quality: **{retrieval.get('quality_grade', 'NOT_RUN')}** "
            f"({retrieval.get('quality_score', 0)}/100)",
            f"Requirements: {retrieval.get('requirements', 0)}; "
            f"retrieved: {retrieval.get('retrieved', 0)}; "
            f"sources: {retrieval.get('source_count', 0)}.",
            f"Failed or unresolved: {', '.join(retrieval.get('failed', [])) or 'none'}",
            "",
            "## Portfolio",
            "",
            f"NAV: **${performance.get('nav', 'UNKNOWN')}**",
            f"Cash: **${performance.get('cash', portfolio.get('cash', 'UNKNOWN'))}**",
            f"Market value: **${performance.get('market_value', 'UNKNOWN')}**",
            f"Realized P&L: **${portfolio.get('realized_pnl', 'UNKNOWN')}**",
            "",
            "## Performance",
            "",
            f"Daily return: **{performance.get('daily_return', 'NOT_AVAILABLE')}**",
            f"Since inception: **{performance.get('cumulative_return', 'NOT_AVAILABLE')}**",
            f"{performance.get('benchmark_symbol', 'SPY')} since inception: **{performance.get('benchmark_cumulative_return', 'NOT_AVAILABLE')}**",
            f"Excess return: **{performance.get('excess_return', 'NOT_AVAILABLE')}**",
            f"Drawdown: **{performance.get('drawdown', 'NOT_AVAILABLE')}**",
            "",
        ]
        lines.extend(["", "### Evidence sources (expandable)", ""])
        if isinstance(evidence_catalog, list) and evidence_catalog:
            lines.extend(
                f"- {item.get('symbol', '?')} / {item.get('field', '?')}: "
                f"{item.get('provider', '?')} @ {item.get('source', '?')} "
                f"(confidence {item.get('confidence', '?')}, "
                f"validated {item.get('validation_status', '?')})"
                for item in evidence_catalog
                if isinstance(item, dict)
            )
        else:
            lines.append("- No evidence catalog was produced.")
        lines.extend(["", "## Positions", ""])
        positions = portfolio.get("positions", [])
        if isinstance(positions, list) and positions:
            lines.extend(
                f"- {item.get('ticker')}: {item.get('quantity')} shares @ average ${item.get('average_cost')}"
                for item in positions
                if isinstance(item, dict)
            )
        else:
            lines.append("- No open positions.")
        lines.extend(
            [
                "",
                "## Market",
                "",
                f"Status: **{market.get('status', 'NOT_RUN')}**; session: **{market.get('session', 'UNKNOWN')}**.",
                "Public observations are research quotes only; quote certification remains BLOCKED.",
                "",
                "## Today's Decisions",
                "",
                f"Deterministic decision: **{decision.get('status', 'NOT_RUN')}**.",
                f"Paper order intents: **{execution.get('intent_count', 0)}**.",
                "",
                "## Risk",
                "",
                "Existing long-only, cash reserve, position, concentration and turnover constraints were applied.",
                "",
                "## Today's Paper Trades",
                "",
            ]
        )
        fills = execution.get("fills", [])
        if isinstance(fills, list) and fills:
            lines.extend(
                f"- {item.get('side')} {item.get('quantity')} {item.get('ticker')} @ ${item.get('fill_price')} (fees ${item.get('fees')})"
                for item in fills
                if isinstance(item, dict)
            )
        else:
            lines.append("- No paper fills.")
        lines.extend(
            [
                "",
                "## Research",
                "",
                "Research: **CODEX / GPT**",
                f"Status: **{research_context.get('status', 'NOT_RUN')}**",
                f"Model: **{research_diagnostics.get('model_requested', research.get('model', 'CLI_DEFAULT'))}**",
                f"Reasoning: **{research_diagnostics.get('reasoning_effort', 'medium')}**",
                f"Structured validation: **{'PASS' if research_diagnostics.get('schema_valid') else 'FAIL'}**",
                f"Confidence: **{research_response.get('confidence', 'NOT_AVAILABLE')}**",
                f"Recommendation: **{research_response.get('recommended_action', 'NO_ACTION')}**",
                f"Elapsed: **{research_diagnostics.get('elapsed_ms', 0)} ms**",
                f"Diagnostic: **{research.get('error_code') or 'none'}**",
                "",
                "## Forward Evidence",
                "",
                f"Status: **{forward.get('status', 'NOT_RUN')}**. Evidence never grants automatic promotion.",
                "",
                "## Gates",
                "",
            ]
        )
        gates = decision.get("gates", [])
        if isinstance(gates, list) and gates:
            lines.extend(
                f"- {gate.get('gate')}: **{gate.get('status')}** — {gate.get('reason')}"
                for gate in gates
                if isinstance(gate, dict)
            )
        else:
            lines.append("- No gate evidence was produced.")
        lines.extend(
            [
                "",
                "## Readiness",
                "",
                f"Paper execution: **{execution.get('status', 'BLOCKED')}**",
                f"Recommendation readiness: **{payload.get('recommendation_readiness', 'BLOCKED')}**",
                f"Manual authority: **{payload.get('manual_authority', 'BLOCKED')}**",
                "Quote certification: **BLOCKED** — public research quotes are not certified execution quotes.",
                "",
                "## Blockers",
                "",
            ]
        )
        blockers = payload.get("blockers", [])
        if isinstance(blockers, list) and blockers:
            lines.extend(f"- {item}" for item in blockers)
        else:
            lines.append("- None.")
        lines.extend(["", "## Next action", ""])
        next_actions = payload.get("next_actions", [])
        if isinstance(next_actions, list):
            lines.extend(f"- {item}" for item in next_actions)
        lines.extend(
            [
                "",
                "PAPER ACCOUNT ONLY. BROKER SUBMISSION = DISABLED. PUBLIC QUOTES = UNCERTIFIED.",
                "",
            ]
        )
        temporary_md = markdown_path.with_suffix(".tmp")
        temporary_md.write_text("\n".join(lines), encoding="utf-8")
        publish_staged_report(temporary_md, markdown_path)
        outputs = {"paper_report_json": str(json_path), "paper_report_markdown": str(markdown_path)}
        try:
            outputs["run_health_json"] = str(persist_run_health(payload, self.paths))
        except OSError as error:
            logging.getLogger("meridian.run_health").error(
                "RUN_HEALTH_PERSISTENCE_FAILED error_type=%s", type(error).__name__
            )
            outputs["run_health_error"] = "RUN_HEALTH_PERSISTENCE_FAILED"
        return outputs

    def paper_run(self, account_name: str = DEFAULT_ACCOUNT) -> dict[str, object]:
        """Run the existing canonical daily flow against one durable paper account."""
        initialized = self.init()
        if initialized["status"] == "INIT_FAILED":
            return {
                **initialized,
                "status": "PAPER_BLOCKED",
                "paper_execution": {"status": "BLOCKED"},
            }
        ledger = self._paper_ledger()
        account = ledger.state(account_name)
        auto_initialized = False
        if account is None:
            if account_name != DEFAULT_ACCOUNT:
                raise ValueError("PAPER_ACCOUNT_NOT_FOUND")
            _, auto_initialized = ledger.initialize(account_name)
        snapshot_path = ledger.write_snapshot(self.paths.cache / "paper-snapshots", account_name)
        previous_llm_mode = os.environ.get("MERIDIAN_LLM_MODE")
        explicit_host_handoff = bool(
            os.environ.get("MERIDIAN_HOST_JOB")
            or os.environ.get("MERIDIAN_HOST_RESULT")
        )
        if explicit_host_handoff:
            os.environ["MERIDIAN_LLM_MODE"] = "HOST_CODEX"
        try:
            # Normal local paper runs execute the configured native runtime.
            # HOST_CODEX is reserved for an explicit job/result handoff.
            daily = self.daily(snapshot_path, research_live_enabled=True)
        finally:
            if explicit_host_handoff:
                if previous_llm_mode is None:
                    os.environ.pop("MERIDIAN_LLM_MODE", None)
                else:
                    os.environ["MERIDIAN_LLM_MODE"] = previous_llm_mode
            try:
                snapshot_path.unlink(missing_ok=True)
            except OSError:
                # A sanitized paper export is still not used as a fallback input.
                pass
        quotes = self._paper_quotes(daily)
        cutoff_text = str(daily.get("information_cutoff") or daily.get("analysis_time"))
        try:
            cutoff = datetime.fromisoformat(cutoff_text)
            market_session = market_status(cutoff).status.value
        except ValueError:
            market_session = "CLOSED"
        trading_date = str(
            daily.get("trading_date") or datetime.now(ZoneInfo("America/New_York")).date()
        )
        canonical_run_id = str(daily.get("run_id", "UNAVAILABLE"))
        report_status = str(daily.get("status", "FAILED"))
        data_status = str(daily.get("data_status", "FAILED"))
        research_status = str(daily.get("research_status", "NOT_RUN"))
        portfolio = daily.get("portfolio")
        targets = portfolio.get("positions", []) if isinstance(portfolio, dict) else []
        blockers: list[str] = []
        fatal_blockers: list[str] = []
        if str(daily.get("runtime_status", "FAILED")) != "PASS":
            fatal_blockers.append("PAPER_CANONICAL_RUNTIME_FAILED")
        if market_session != MarketStatus.OPEN.value:
            blockers.append("PAPER_EXECUTION_BLOCKED_MARKET_CLOSED")
        expected_closed_market = (
            market_session != MarketStatus.OPEN.value and data_status == "MARKET_CLOSED"
        )
        if (data_status != "PASS" or not quotes) and not expected_closed_market:
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_MARKET_DATA")
        if research_status != "AVAILABLE":
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_RESEARCH_" + research_status)
        expected_closed_decision = (
            expected_closed_market and report_status == RunStatus.BLOCKED_STALE_MARKET.value
        )
        if report_status not in {"DRAFT", "NO_ACTION"} and not expected_closed_decision:
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_DECISION_" + report_status)
        if report_status == "DRAFT" and not isinstance(targets, list):
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_DECISION_CONTEXT")
        blockers.extend(fatal_blockers)

        execution_status = (
            "PAPER_WAITING_FOR_MARKET"
            if expected_closed_market and not fatal_blockers
            else "PAPER_BLOCKED"
        )
        fills = ()
        intents = ()
        if not blockers:
            previous = ledger.daily_execution(account_name, trading_date)
            if previous is not None:
                execution_status = "PAPER_ALREADY_EXECUTED"
                blockers.append("PAPER_DAILY_IDEMPOTENCY_ALREADY_EXECUTED")
            else:
                policies = load_policies(policy_directory())
                if report_status == "NO_ACTION":
                    execution_status, paper_fills = ledger.execute(
                        account_name,
                        trading_date=trading_date,
                        canonical_run_id=canonical_run_id,
                        intents=(),
                    )
                else:
                    paper_intents = ledger.build_order_intents(
                        account_name,
                        trading_date=trading_date,
                        canonical_run_id=canonical_run_id,
                        targets=targets,
                        quotes=quotes,
                        risk=policies.risk,
                        execution=policies.execution,
                    )
                    intents = paper_intents
                    execution_status, paper_fills = ledger.execute(
                        account_name,
                        trading_date=trading_date,
                        canonical_run_id=canonical_run_id,
                        intents=paper_intents,
                    )
                fills = paper_fills
        paper_fills = tuple(fills)
        performance = ledger.record_nav(
            account_name,
            trading_date=trading_date,
            canonical_run_id=canonical_run_id,
            quotes=quotes,
            fills=paper_fills,
        )
        account_status = ledger.status(account_name)
        paper_run_id = "paper-" + canonical_run_id
        paper_execution = {
            "status": execution_status,
            "readiness": "PASS"
            if execution_status in {"PAPER_COMPLETE", "PAPER_NO_TRADE"}
            else "BLOCKED",
            "authority": "PAPER_EXECUTION_ONLY",
            "quote_kind": "PUBLIC_RESEARCH_QUOTE",
            "quote_certification": "BLOCKED",
            "market_session": market_session,
            "intent_count": len(intents),
            "fills": [item.as_dict() for item in paper_fills],
            "slippage_bps": str(ledger.settings.slippage_bps),
            "commission_per_order": str(ledger.settings.commission_per_order),
        }
        final_status = (
            "PAPER_READY" if execution_status == "PAPER_COMPLETE" else execution_status
        )
        daily_readiness = daily.get("readiness")
        daily_readiness = daily_readiness if isinstance(daily_readiness, dict) else {}
        daily_manual_authority = daily.get("manual_authority")
        daily_manual_authority = (
            daily_manual_authority if isinstance(daily_manual_authority, dict) else {}
        )
        payload: dict[str, object] = {
            "schema_version": "meridian-paper-daily.v1",
            "paper_run_id": paper_run_id,
            "canonical_run_id": canonical_run_id,
            "analysis_time": daily.get("analysis_time", datetime.now(UTC).isoformat()),
            "trading_date": trading_date,
            "status": final_status,
            "runtime_status": daily.get("runtime_status", "FAILED"),
            "account": account_status,
            "portfolio": {
                "cash": account_status.get("cash"),
                "realized_pnl": account_status.get("realized_pnl"),
                "positions": account_status.get("positions", []),
            },
            "performance": performance
            or {"status": "NOT_MARKED", "reason": "FRESH_QUOTES_FOR_ALL_POSITIONS_REQUIRED"},
            "startup_diagnostics": daily.get("startup_diagnostics", {}),
            "execution_mode": daily.get("execution_mode", "SAFE_ANALYSIS"),
            "safe_analysis": daily.get("safe_analysis", {}),
            "market": {
                "status": data_status,
                "session": market_session,
                "market_data_tradeable": bool(
                    daily.get(
                        "market_data_tradeable",
                        market_session == MarketStatus.OPEN.value and data_status == "PASS",
                    )
                ),
                "observations": quotes,
                "provider_probes": daily.get("provider_probes", {}),
                "quote_certification": "BLOCKED",
            },
            "research": daily.get("research", {"status": research_status}),
            "data_auto_retrieval": daily.get("data_auto_retrieval", {}),
            "research_universe": daily.get("research_universe", {}),
            "forward_evidence": daily.get("forward_evidence", {"status": "NOT_RUN"}),
            "decision": {
                "status": report_status,
                "context": daily.get("decision_context"),
                "gates": daily.get("gates", []),
            },
            "paper_execution": paper_execution,
            "recommendation_readiness": daily_readiness.get("recommendation_readiness", "BLOCKED"),
            "manual_authority": daily_manual_authority.get("status", "BLOCKED"),
            "quote_certification": "BLOCKED",
            "auto_initialized": auto_initialized,
            "blockers": blockers,
            "next_actions": (
                [
                    "Inspect canonical report and retry only during a regular session with fresh public data and validated advisory research."
                ]
                if blockers
                else ["Paper ledger and report were updated. Broker submission remains disabled."]
            ),
            "canonical_output_files": daily.get("output_files", {}),
        }
        try:
            paper_outputs = self._persist_paper_report(payload)
        except OSError:
            paper_outputs = {}
            payload["blockers"] = [*blockers, "PAPER_REPORT_WRITE_FAILED"]
            payload["next_actions"] = [
                "Check report directory permissions and preserve the canonical report and paper ledger."
            ]
        payload["output_files"] = {
            **paper_outputs,
            **({"canonical_report_json": daily["report_json"]} if "report_json" in daily else {}),
            **(
                {"canonical_report_markdown": daily["report_markdown"]}
                if "report_markdown" in daily
                else {}
            ),
        }
        return payload

    def shadow_run(self, market_fixture: Path) -> dict[str, object]:
        """Run live GPT against bounded market facts with permanently zero orders."""
        self.paths.ensure_directories()
        policies = load_policies(policy_directory())
        settings = policies.models.research
        if settings is None:
            raise ValueError("SHADOW_RESEARCH_NOT_CONFIGURED")
        quotes = load_market_fixture(market_fixture)
        cutoff = datetime.now(UTC)
        observations = tuple(
            PublicResearchObservation(
                ticker=ticker,
                observed_at=quote.timestamp,
                price=quote.last,
                daily_return=quote.daily_return,
                reference=hashlib.sha256(
                    json.dumps(quote.model_dump(mode="json"), sort_keys=True).encode()
                ).hexdigest(),
            )
            for ticker, quote in sorted(quotes.items())
            if ticker in policies.universe.tickers and quote.timestamp <= cutoff
        )
        request = DailyResearchInput(
            parent_run_id="shadow-" + uuid4().hex,
            analysis_cutoff=cutoff,
            mode="LIVE",
            snapshot_reference="SHADOW_NO_ACCOUNT_SNAPSHOT",
            market_reference=hashlib.sha256(
                json.dumps({ticker: quote.model_dump(mode="json") for ticker, quote in quotes.items()}, sort_keys=True, default=str).encode()
            ).hexdigest(),
            temporal_context=ResearchTemporalContext(
                run_id="shadow-context-" + cutoff.strftime("%Y%m%dT%H%M%S%fZ"),
                trading_date=cutoff.astimezone(ZoneInfo("America/New_York")).date(),
                as_of=cutoff,
                information_cutoff=cutoff,
                market_session=market_status(cutoff).status.value,
                timezone="America/New_York",
            ),
            policy_reference=hashlib.sha256(policies.models.model_dump_json().encode()).hexdigest(),
            provider=settings.provider,
            model=settings.model,
            observations=observations,
            freshness_status="PASS" if observations else "BLOCKED",
            provider_provenance={ticker: "FIXTURE_SHADOW" for ticker in quotes},
        )
        record = ShadowResearchRunner(self.paths).run(
            request,
            settings.model_copy(update={"live_enabled": True}),
            mode=ShadowMode.SHADOW_LIVE,
            run_id=request.parent_run_id,
            market_closed=market_status(cutoff).status is not MarketStatus.OPEN,
        )
        directory = self.paths.reports / cutoff.date().isoformat() / record.run_id
        return {
            **record.model_dump(mode="json"),
            "output_files": {"shadow_research_json": str(directory / "shadow_research.json")},
            "orders_created": 0,
            "orders_executed": 0,
            "shadow_only": True,
        }
    def data_status(self) -> dict[str, object]:
        policies = load_policies(policy_directory())
        snapshot = OperationalMarketSnapshotService.from_runtime(
            self.paths,
            policy=FreshnessPolicy(
                quote_max_age_seconds=policies.data.quote_max_age_seconds,
                account_max_age_seconds=policies.data.account_snapshot_max_age_seconds,
            ),
        ).build(policies.universe.tickers, analysis_time=datetime.now().astimezone(), live=True)
        return {
            **snapshot.data_status(),
            "status": "PASS" if snapshot.status == "OPERATIONAL_READY" else "DEGRADED",
        }

    def dip_scout(self, packet_path: Path) -> dict[str, object]:
        return dip_scout(
            ResearchPacket.model_validate_json(packet_path.read_text(encoding="utf-8"))
        )

    def forward_status(self) -> dict[str, object]:
        policy = load_forward_evidence_policy(policy_directory())
        ledger = ForwardLedger(self.paths.audit / "forward-evidence.json")
        return {
            **ledger.evaluate(minimum_samples=policy.minimum_mature_samples),
            "policy_hash": forward_policy_hash(policy),
            "authority": "SHADOW_EVIDENCE_ONLY_NO_AUTOMATIC_PROMOTION",
        }

    def latest_report(self) -> dict[str, object]:
        reports = sorted(
            self.paths.reports.glob("*/*/daily.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not reports:
            return {"found": False, "status": "REPORT_NOT_FOUND"}
        raw = json.loads(reports[0].read_text(encoding="utf-8"))
        safe_keys = (
            "run_id",
            "readiness",
            "status",
            "analysis_time",
            "information_cutoff",
            "data_mode",
            "execution",
            "broker_submission",
            "blocked_reasons",
            "provider_health",
            "symbols_missing",
        )
        return {
            "found": True,
            "status": "OK",
            "report": {key: raw.get(key) for key in safe_keys},
            "execution": "MANUAL",
            "broker_submission": "DISABLED",
        }
