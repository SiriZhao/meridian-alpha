"""Canonical application facade: CLI/MCP call this, domain code stays below."""

from __future__ import annotations

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
    load_market_fixture,
    persist_report,
    persist_run_report,
)
from meridian.forward_evidence import ForwardLedger
from meridian.host_readiness import (
    ReadinessStatus,
    RecommendationReadiness,
    SnapshotDiagnostic,
    inspect_snapshot,
)
from meridian.intelligence import ResearchPacket
from meridian.intelligence_tools import dip_scout
from meridian.operational_data import FreshnessPolicy
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.runtime import RuntimePaths, policy_directory
from meridian.runtime_diagnostics import report as doctor_report


class MeridianApplicationService:
    """Thin canonical application layer; it owns no allocator, risk, or pricing logic."""

    def __init__(self, paths: RuntimePaths | None = None) -> None:
        self.paths = paths or RuntimePaths.from_environment()

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
        logger.info("Market retrieval complete; deterministic analysis started")
        result = DailyClosureService(policies).run(account, quotes, cutoff=cutoff)
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
            "research_status": "NOT_RUN",
            "quant_status": "PASS" if result.decision.target_portfolio is not None else "NOT_RUN",
            "risk_status": "PASS" if result.decision.target_portfolio is not None and analysis_ok else "NOT_RUN",
            "recommendation_status": "RESEARCH_ONLY" if analysis_ok else "BLOCKED",
            "warnings": ["LLM_RESEARCH_NOT_CONNECTED_TO_CANONICAL_DAILY", "NOT_AUTHORIZED_FOR_MANUAL_ENTRY"],
            "errors": list(result.decision.blocked_reasons) + ([market_error] if market_error else []),
            "output_files": {"report_json": str(directory / "daily.json"), "report_markdown": str(directory / "daily.md"), "log": str(log_path)},
            "elapsed_seconds": round(monotonic() - started, 3),
        })
        market_ok = result.report["data_status"] == "PASS"
        snapshot_fresh = (cutoff - account.as_of).total_seconds() <= policies.data.account_snapshot_max_age_seconds
        ready = RecommendationReadiness(
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
        result.report.update({"readiness": ready.model_dump(mode="json"),
            "snapshot_provenance": snapshot.model_dump(mode="json"),
            "next_actions": ["Provide verifiable authorized Host source evidence; content hashes are not authentication.",
                             "Supply fresh market observations if freshness is blocked.",
                             "Run certified research and policy gates before recommendation readiness.",
                             "Manual entry additionally requires a certified execution quote and sealed authority."],
            "degraded_reasons": ["RESEARCH_NOT_RUN", "POLICY_SECURITY_METADATA_UNCERTIFIED", "PUBLIC_QUOTE_UNCERTIFIED"],
        })
        AuditStore(self.paths.db).write_decision(result.decision)
        AuditStore(self.paths.db).write_readiness(result.decision.run_id, cutoff.isoformat(), str(result.report["status"]), {
            "readiness": result.report["readiness"], "snapshot_provenance": result.report["snapshot_provenance"],
            "provider_probes": provenance.get("provider_probes", {}), "data_mode": provenance["data_mode"],
            "next_actions": result.report["next_actions"], "errors": result.report["errors"], "error_code": result.report.get("error_code"),
        })
        logger.info("run_id=%s data_mode=%s elapsed_seconds=%s", result.decision.run_id, provenance["data_mode"], result.report["elapsed_seconds"])
        logger.info("recommendation=%s blockers=%s", ready.recommendation_readiness.value, ready.blockers)
        logger.warning("Research NOT_RUN; outputs are research-only, no manual-entry authority")
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
