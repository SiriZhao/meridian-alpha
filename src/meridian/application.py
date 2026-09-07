"""Canonical application facade: CLI/MCP call this, domain code stays below."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from meridian.audit import SCHEMA_VERSION, AuditStore
from meridian.config import load_policies
from meridian.daily_closure import (
    DailyClosureService,
    daily_run_id,
    load_market_fixture,
    persist_report,
    persist_run_report,
)
from meridian.daily_research import (
    DailyResearchInput,
    PublicResearchObservation,
    ResearchProviderStatus,
)
from meridian.forward_evidence import ForwardLedger
from meridian.host_readiness import (
    ReadinessGateResult,
    ReadinessStatus,
    RecommendationReadiness,
    SnapshotDiagnostic,
    inspect_snapshot,
)
from meridian.intelligence import ResearchPacket
from meridian.intelligence_tools import dip_scout
from meridian.operational_data import FreshnessPolicy
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.research_stage import CanonicalResearchStage
from meridian.runtime import RuntimePaths, policy_directory
from meridian.runtime_diagnostics import report as doctor_report


class MeridianApplicationService:
    """Thin canonical application layer; it owns no allocator, risk, or pricing logic."""

    def __init__(self, paths: RuntimePaths | None = None, *, research_stage: CanonicalResearchStage | None = None) -> None:
        self.paths = paths or RuntimePaths.from_environment()
        self.research_stage = research_stage or CanonicalResearchStage()

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
            with closing(sqlite3.connect(self.paths.db.resolve().as_uri() + "?mode=rw", uri=True)) as connection:
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
        diagnostic, _ = inspect_snapshot(path, max_age_seconds=policies.data.account_snapshot_max_age_seconds)
        diagnostic = self._snapshot_novelty(diagnostic, claim=False)
        return {"valid": diagnostic.status is ReadinessStatus.PASS,
                "status": "PASS" if diagnostic.status is ReadinessStatus.PASS else "DEGRADED",
                "snapshot_provenance": diagnostic.model_dump(mode="json"), "sanitized": True}

    def _snapshot_novelty(self, diagnostic: SnapshotDiagnostic, *, claim: bool) -> SnapshotDiagnostic:
        if diagnostic.status is not ReadinessStatus.PASS or diagnostic.snapshot_key is None or diagnostic.content_hash is None:
            return diagnostic
        novelty = AuditStore(self.paths.db).snapshot_novelty(diagnostic.snapshot_key, diagnostic.content_hash,
            seen_at=diagnostic.checked_at.isoformat() if claim else None)
        return diagnostic.model_copy(update={"novelty": novelty, **(
            {"status": ReadinessStatus.BLOCKED, "code": "ACCOUNT_SNAPSHOT_REPLAYED" if novelty == "REPLAYED" else "ACCOUNT_SNAPSHOT_ID_CONFLICT"}
            if novelty != "NEW" else {})})

    def _rejected_snapshot(self, diagnostic: SnapshotDiagnostic, log_path: Path) -> dict[str, object]:
        now = datetime.now(UTC)
        run_id = "daily-" + uuid4().hex
        ready = RecommendationReadiness(runtime_health=ReadinessStatus.PASS,
            account_snapshot_status=diagnostic.status, account_snapshot_freshness=diagnostic.freshness,
            account_provenance=diagnostic.provenance_status,
            market_data_status=ReadinessStatus.NOT_RUN, market_data_freshness=ReadinessStatus.NOT_RUN,
            quote_certification_status=ReadinessStatus.BLOCKED, quote_kind="NOT_REQUESTED",
            input_mode=diagnostic.source_kind or "UNKNOWN")
        directory = self.paths.reports / now.date().isoformat() / run_id
        payload: dict[str, object] = {
            "run_id": run_id, "analysis_time": now.isoformat(), "timestamp": now.isoformat(),
            "trading_date": now.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
            "status": "BLOCKED_STALE_ACCOUNT", "runtime_status": "PASS",
            "readiness": ready.model_dump(mode="json"),
            "snapshot_provenance": diagnostic.model_dump(mode="json"),
            "data_status": "NOT_RUN", "research_status": "NOT_RUN", "quant_status": "NOT_RUN", "risk_status": "NOT_RUN",
            "recommendation_status": "BLOCKED", "blocked_reasons": [diagnostic.code],
            "errors": [diagnostic.code], "warnings": [], "orders": [],
            "next_actions": [diagnostic.next_action], "provider_probes": {},
            "research": {"context": {"status": "NOT_RUN", "output": None, "authority": "ADVISORY_ONLY"},
                         "provenance": "NONE", "attempts": 0, "error_code": "RESEARCH_UPSTREAM_BLOCKED",
                         "next_action": diagnostic.next_action},
            "decision_context": {"research_status": "NOT_RUN", "research": None},
            "gates": [ReadinessGateResult(gate=name, status=ReadinessStatus.NOT_RUN,
                        reason="Snapshot validation prevented evaluation", evidence=(diagnostic.code,)).model_dump(mode="json")
                      for name in ("ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY",
                                   "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY")],
            "manual_authority": {"status": "BLOCKED", "certificate_issued": False},
            "stages": [{"stage": name, "run_id": run_id, "start": None, "finish": None,
                        "duration_seconds": 0, "status": "NOT_RUN", "error_code": "UPSTREAM_SNAPSHOT_BLOCKED",
                        "next_action": diagnostic.next_action} for name in ("market", "research", "decision")],
            "execution": "MANUAL", "broker_submission": "DISABLED",
            "output_files": {"report_json": str(directory / "daily.json"), "report_markdown": str(directory / "daily.md"), "log": str(log_path)},
        }
        AuditStore(self.paths.db).write_readiness(run_id, now.isoformat(), str(payload["status"]), payload)
        j, m = persist_run_report(payload, self.paths)
        return {**payload, "report_json": str(j), "report_markdown": str(m)}

    def daily(self, snapshot_path: Path | None, market_fixture: Path | None = None) -> dict[str, object]:
        self.paths.ensure_directories()
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
            return self._daily(snapshot_path, market_fixture, logger, log_path)
        except (OSError, ValueError, sqlite3.Error):
            logger.error("Daily failed; run doctor and validate input. Exception details omitted to protect account data.")
            raise
        finally:
            logger.info("END invocation=%s", invocation)
            logger.removeHandler(handler)
            handler.close()

    def _daily(self, snapshot_path: Path | None, market_fixture: Path | None, logger: logging.Logger, log_path: Path) -> dict[str, object]:
        started = monotonic()
        logger.info("Database initialization and preflight started")
        initialized = self.init()
        if initialized["status"] == "INIT_FAILED":
            return {**initialized, "run_id": log_path.stem, "runtime_status": "FAILED",
                    "readiness": RecommendationReadiness(runtime_health=ReadinessStatus.FAILED).model_dump(mode="json"),
                    "errors": [initialized["error_code"]], "next_actions": [initialized["next_step"]], "output_files": {"log": str(log_path)}}
        preflight = self.doctor()
        if preflight["status"] == "FAIL":
            return {"status": "FAILED", "run_id": log_path.stem, "runtime_status": "FAILED", "error_code": "MERIDIAN_PREFLIGHT_FAILED", "diagnostics": preflight, "readiness": RecommendationReadiness(runtime_health=ReadinessStatus.FAILED).model_dump(mode="json"), "errors": ["MERIDIAN_PREFLIGHT_FAILED"], "next_actions": ["Resolve failed doctor checks."], "output_files": {"log": str(log_path)}}
        logger.info("Database status=%s", initialized["status"])
        policies = load_policies(policy_directory())
        snapshot, account = inspect_snapshot(snapshot_path, max_age_seconds=policies.data.account_snapshot_max_age_seconds)
        snapshot = self._snapshot_novelty(snapshot, claim=True)
        if snapshot.status is not ReadinessStatus.PASS or account is None:
            logger.warning("Snapshot rejected code=%s", snapshot.code)
            return self._rejected_snapshot(snapshot, log_path)
        cutoff = datetime.now(UTC)
        market_started = cutoff
        logger.info("Market retrieval started; mode=%s", "FIXTURE" if market_fixture else "OPERATIONAL_PUBLIC")
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
            provenance: dict[str, object] = {
                "data_mode": "FIXTURE",
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
            operational = OperationalMarketSnapshotService.from_runtime(self.paths, policy=FreshnessPolicy(quote_max_age_seconds=policies.data.quote_max_age_seconds, account_max_age_seconds=policies.data.account_snapshot_max_age_seconds)).build(
                symbols, analysis_time=cutoff, live=True
            )
            cutoff = operational.information_cutoff
            quotes = operational.quotes if not operational.missing_symbols else {}
            provenance = {
                "data_mode": operational.data_mode,
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
        closure = DailyClosureService(policies)
        parent_id = daily_run_id(account, quotes, cutoff, policies)
        settings = policies.models.research
        def digest(value: object) -> str:
            return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
        health = provenance.get("provider_health")
        health = health if isinstance(health, dict) else {}
        input_blockers = closure._gates(account, quotes, cutoff)
        inputs_ready = not input_blockers
        market_valid = bool(quotes) and not any("MARKET" in reason for reason in input_blockers)
        request = DailyResearchInput(parent_run_id=parent_id, analysis_cutoff=cutoff,
            mode="FIXTURE" if market_fixture or snapshot.source_kind == "FIXTURE" else "LIVE",
            snapshot_reference=snapshot.content_hash or "UNAVAILABLE",
            market_reference=digest({symbol: quote.model_dump(mode="json") for symbol, quote in quotes.items()}),
            policy_reference=digest({name: value.model_dump(mode="json") for name, value in vars(policies).items()}),
            provider=settings.provider if settings else "UNCONFIGURED", model=settings.model if settings else "UNCONFIGURED",
            observations=tuple(PublicResearchObservation(ticker=ticker, observed_at=quote.timestamp,
                price=quote.last, daily_return=quote.daily_return, reference=digest(quote.model_dump(mode="json")))
                for ticker, quote in sorted(quotes.items()) if ticker in policies.universe.tickers and inputs_ready),
            freshness_status="PASS" if inputs_ready else "BLOCKED",
            provider_provenance={ticker: json.dumps(health, sort_keys=True) for ticker, health in health.items()},
        )
        logger.info("run_id=%s stage=research start", parent_id)
        research = self.research_stage.run(request, settings)
        logger.info("run_id=%s stage=research status=%s duration=%s code=%s", parent_id, research.context.status.value, research.duration_seconds, research.error_code)
        evaluated_at = datetime.now(UTC)
        result = closure.run(account, quotes, cutoff=cutoff, research=research.context, evaluated_at=evaluated_at)
        result.report.update({"research": research.model_dump(mode="json"), "research_input": request.model_dump(mode="json"),
            "stages": [
                {"stage": "market", "run_id": parent_id, "start": market_started.isoformat(), "finish": market_finished.isoformat(), "duration_seconds": (market_finished - market_started).total_seconds(), "status": "PASS" if market_valid else "BLOCKED", "error_code": market_error or (None if market_valid else "MARKET_INPUT_NOT_READY"), "next_action": "Review provider probes and freshness."},
                {"stage": "research", "run_id": parent_id, "start": research.started_at.isoformat(), "finish": research.finished_at.isoformat(), "duration_seconds": research.duration_seconds, "status": research.context.status.value, "error_code": research.error_code, "next_action": research.next_action},
                {"stage": "decision", "run_id": parent_id, "start": evaluated_at.isoformat(), "finish": datetime.now(UTC).isoformat(), "duration_seconds": (datetime.now(UTC) - evaluated_at).total_seconds(), "status": result.decision.overall_status.value, "error_code": None, "next_action": "Review deterministic policy gates; no manual authority inferred."},
            ]})
        result.report.update(provenance)
        if market_error:
            result.report.update({"error_code": market_error, "exit_code": 3, "error_category": "DATA_QUALITY"})
        analysis_ok = result.report["status"] in {"DRAFT", "NO_ACTION", "NO_CAPITAL"}
        directory = self.paths.reports / result.decision.as_of.date().isoformat() / result.decision.run_id
        result.report.update({
            "timestamp": cutoff.isoformat(),
            "trading_date": cutoff.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
            "runtime_status": "PASS",
            "database_status": "PASS",
            "data_status": "PASS" if quotes and not any("MARKET" in reason for reason in result.decision.blocked_reasons) else "FAILED",
            "portfolio_status": account.freshness_state.value,
            "research_status": research.context.status.value,
            "quant_status": "PASS" if result.decision.target_portfolio is not None else "NOT_RUN",
            "risk_status": "PASS" if result.decision.target_portfolio is not None and analysis_ok else "NOT_RUN",
            "recommendation_status": "RESEARCH_ONLY" if analysis_ok else "BLOCKED",
            "warnings": ["PUBLIC_RESEARCH_IS_ADVISORY_NOT_CERTIFIED", "NOT_AUTHORIZED_FOR_MANUAL_ENTRY"],
            "errors": list(result.decision.blocked_reasons) + ([market_error] if market_error else []),
            "output_files": {"report_json": str(directory / "daily.json"), "report_markdown": str(directory / "daily.md"), "log": str(log_path)},
            "elapsed_seconds": round(monotonic() - started, 3),
        })
        market_ok = result.report["data_status"] == "PASS"
        snapshot_fresh = (evaluated_at - account.as_of).total_seconds() <= policies.data.account_snapshot_max_age_seconds
        research_available = research.context.status is ResearchProviderStatus.AVAILABLE
        research_health = ReadinessStatus.PASS if research_available else ReadinessStatus.NOT_RUN if research.context.status is ResearchProviderStatus.NOT_RUN else ReadinessStatus.BLOCKED
        ready = RecommendationReadiness(
            research_status=research_health,
            research_freshness=ReadinessStatus.PASS if research_available and research.response_received_at is not None and 0 <= (evaluated_at - research.response_received_at).total_seconds() <= (settings.live_as_of_tolerance_seconds if settings else 0) else ReadinessStatus.UNKNOWN,
            runtime_health=ReadinessStatus(str(preflight["status"])),
            account_snapshot_status=snapshot.status,
            account_snapshot_freshness=ReadinessStatus.PASS if snapshot_fresh else ReadinessStatus.BLOCKED,
            account_provenance=snapshot.provenance_status,
            market_data_status=ReadinessStatus.PASS if quotes else ReadinessStatus.BLOCKED,
            market_data_freshness=ReadinessStatus.PASS if market_ok else ReadinessStatus.BLOCKED,
            provider_provenance=ReadinessStatus.DEGRADED if market_fixture else ReadinessStatus.PASS if provenance.get("provider_probes") else ReadinessStatus.UNKNOWN,
            decision_pipeline_status=ReadinessStatus.PASS if result.decision.target_portfolio is not None and analysis_ok else ReadinessStatus.FAILED if result.report["status"] == "FAILED" else ReadinessStatus.NOT_RUN,
            policy_gate_status=ReadinessStatus.DEGRADED if result.decision.target_portfolio is not None else ReadinessStatus.NOT_RUN,
            quote_certification_status=ReadinessStatus.BLOCKED,
            input_mode="FIXTURE" if market_fixture or snapshot.source_kind == "FIXTURE" else "HOST_SUPPLIED_UNVERIFIED",
            quote_kind="PUBLIC_RESEARCH_QUOTE" if not market_fixture else "FIXTURE",
        )
        reconciliation = result.report.get("reconciliation")
        reconciled = isinstance(reconciliation, dict) and reconciliation.get("status") == "DRAFT"
        gate_specs = (
            ("ACCOUNT_READY", ReadinessStatus.PASS if ready.account_provenance is ReadinessStatus.PASS and snapshot_fresh else ReadinessStatus.BLOCKED, "Authenticated fresh Host source required", snapshot.content_hash or "UNAVAILABLE"),
            ("SECURITY_READY", ready.policy_gate_status, "Operational sector metadata is not authoritative certification", request.policy_reference),
            ("MARKET_READY", ready.market_data_freshness, "Market observations must be fresh at decision time", request.market_reference),
            ("RESEARCH_READY", ReadinessStatus.DEGRADED if research_available else research_health, "Public model inference is advisory, not certified evidence", research.context.input_hash),
            ("QUOTE_READY", ready.quote_certification_status, "Certified execution quote absent", "UNAVAILABLE"),
            ("RISK_READY", ReadinessStatus.PASS if result.report["risk_status"] == "PASS" else ReadinessStatus.BLOCKED, "Deterministic projected portfolio validation", request.policy_reference),
            ("RECONCILIATION_READY", ReadinessStatus.PASS if reconciled and snapshot_fresh else ReadinessStatus.BLOCKED, "Reconciliation uses supplied facts; no fills inferred", snapshot.content_hash or "UNAVAILABLE"),
        )
        gates = tuple(ReadinessGateResult(gate=name, status=status, reason=reason, evidence=(reference,)) for name, status, reason, reference in gate_specs)
        result.report.update({"gates": [gate.model_dump(mode="json") for gate in gates],
            "manual_authority": {"status": "BLOCKED" if any(gate.status is not ReadinessStatus.PASS for gate in gates) else "MANUAL_REVIEW_REQUIRED", "certificate_issued": False, "reason": "Existing sealed authority and certified quote remain required."},
            "readiness": ready.model_dump(mode="json"),
            "snapshot_provenance": snapshot.model_dump(mode="json"),
            "next_actions": ["Provide verifiable authorized Host source evidence; content hashes are not authentication.",
                             "Supply fresh market observations if freshness is blocked.",
                             "Run certified research and policy gates before recommendation readiness.",
                             "Manual entry additionally requires a certified execution quote and sealed authority."],
            "degraded_reasons": ["RESEARCH_ADVISORY_ONLY" if research_available else "RESEARCH_" + research.context.status.value, "POLICY_SECURITY_METADATA_UNCERTIFIED", "PUBLIC_QUOTE_UNCERTIFIED"],
        })
        AuditStore(self.paths.db).write_decision(result.decision)
        AuditStore(self.paths.db).write_readiness(result.decision.run_id, cutoff.isoformat(), str(result.report["status"]), {
            "research": result.report["research"], "research_input": result.report["research_input"], "decision_context": result.report["decision_context"], "gates": result.report["gates"], "stages": result.report["stages"], "manual_authority": result.report["manual_authority"],
            "readiness": result.report["readiness"], "snapshot_provenance": result.report["snapshot_provenance"],
            "provider_probes": provenance.get("provider_probes", {}), "data_mode": provenance["data_mode"],
            "next_actions": result.report["next_actions"], "errors": result.report["errors"], "error_code": result.report.get("error_code"),
        })
        logger.info("run_id=%s data_mode=%s elapsed_seconds=%s", result.decision.run_id, provenance["data_mode"], result.report["elapsed_seconds"])
        logger.info("recommendation=%s blockers=%s", ready.recommendation_readiness.value, ready.blockers)
        logger.warning("Research status=%s; advisory-only, no manual-entry authority", research.context.status.value)
        logger.info("status=%s provider_health=%s report=%s", result.report["status"], provenance["provider_health"], directory)
        persisted = persist_report(result, self.paths)
        return {
            **persisted.report,
            "report_json": str(persisted.report_json),
            "report_markdown": str(persisted.report_markdown),
        }

    def data_status(self) -> dict[str, object]:
        policies = load_policies(policy_directory())
        snapshot = OperationalMarketSnapshotService.from_runtime(self.paths, policy=FreshnessPolicy(quote_max_age_seconds=policies.data.quote_max_age_seconds, account_max_age_seconds=policies.data.account_snapshot_max_age_seconds)).build(
            policies.universe.tickers, analysis_time=datetime.now().astimezone(), live=True
        )
        return {**snapshot.data_status(), "status": "PASS" if snapshot.quotes and not snapshot.missing_symbols else "DEGRADED"}

    def dip_scout(self, packet_path: Path) -> dict[str, object]:
        return dip_scout(
            ResearchPacket.model_validate_json(packet_path.read_text(encoding="utf-8"))
        )

    def forward_status(self) -> dict[str, object]:
        ledger = ForwardLedger(self.paths.audit / "forward-evidence.json")
        return ledger.evaluate()

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
