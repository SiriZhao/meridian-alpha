"""Canonical application facade: CLI/MCP call this, domain code stays below."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from meridian.audit import SCHEMA_VERSION, AuditStore
from meridian.config import load_policies
from meridian.daily_closure import (
    DailyClosureService,
    load_market_fixture,
    load_snapshot,
    persist_report,
)
from meridian.forward_evidence import ForwardLedger
from meridian.intelligence import ResearchPacket
from meridian.intelligence_tools import dip_scout
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
        account = load_snapshot(path)
        return {
            "valid": True,
            "snapshot_id": account.snapshot_id,
            "as_of": account.as_of.isoformat(),
            "freshness": account.freshness_state.value,
            "sync": account.sync_state.value,
            "sanitized": True,
        }

    def daily(self, snapshot_path: Path, market_fixture: Path | None = None) -> dict[str, object]:
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

    def _daily(self, snapshot_path: Path, market_fixture: Path | None, logger: logging.Logger, log_path: Path) -> dict[str, object]:
        started = monotonic()
        logger.info("Database initialization and preflight started")
        initialized = self.init()
        if initialized["status"] == "INIT_FAILED":
            return initialized
        preflight = self.doctor()
        if preflight["status"] == "FAIL":
            return {"status": "FAILED", "error_code": "MERIDIAN_PREFLIGHT_FAILED", "diagnostics": preflight}
        logger.info("Database status=%s", initialized["status"])
        account = load_snapshot(snapshot_path)
        policies = load_policies(policy_directory())
        cutoff = datetime.now(account.as_of.tzinfo)
        logger.info("Market retrieval started; mode=%s", "FIXTURE" if market_fixture else "OPERATIONAL_PUBLIC")
        if market_fixture:
            quotes = load_market_fixture(market_fixture)
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
            operational = OperationalMarketSnapshotService.from_runtime(self.paths).build(
                symbols, analysis_time=cutoff, live=True
            )
            cutoff = operational.information_cutoff
            quotes = operational.quotes if not operational.missing_symbols else {}
            provenance = {
                "data_mode": operational.data_mode,
                "market_snapshot_hash": operational.snapshot_hash,
                "information_cutoff": operational.information_cutoff.isoformat(),
                "provider_health": operational.provider_health,
                "cache": operational.cache,
                "provider_conflicts": operational.conflicts,
                "symbols_missing": operational.missing_symbols,
                "research_pit": "BLOCKED",
            }
        logger.info("Market retrieval complete; deterministic analysis started")
        result = DailyClosureService(policies).run(account, quotes, cutoff=cutoff)
        result.report.update(provenance)
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
            "errors": list(result.decision.blocked_reasons),
            "output_files": {"report_json": str(directory / "daily.json"), "report_markdown": str(directory / "daily.md"), "log": str(log_path)},
            "elapsed_seconds": round(monotonic() - started, 3),
        })
        AuditStore(self.paths.db).write_decision(result.decision)
        logger.info("run_id=%s data_mode=%s elapsed_seconds=%s", result.decision.run_id, provenance["data_mode"], result.report["elapsed_seconds"])
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
        snapshot = OperationalMarketSnapshotService.from_runtime(self.paths).build(
            policies.universe.tickers, analysis_time=datetime.now().astimezone(), live=True
        )
        return {**snapshot.data_status(), "status": "PASS" if not snapshot.missing_symbols else "DEGRADED"}

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
