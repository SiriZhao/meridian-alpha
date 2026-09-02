"""Canonical application facade: CLI/MCP call this, domain code stays below."""

from __future__ import annotations

import importlib.metadata
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

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
        return {"project_version": project_version, "python": sys.version.split()[0], "expected_python": "3.12", "supported": sys.version_info[:2] == (3, 12)}

    def paths_status(self) -> dict[str, str]:
        return self.paths.as_dict()

    def doctor(self) -> dict[str, object]:
        return doctor_report(self.paths)

    def init(self) -> dict[str, object]:
        self.paths.ensure_directories()
        existed = self.paths.db.exists()
        try:
            AuditStore(self.paths.db).migrate()
            with sqlite3.connect(f"file:{self.paths.db}?mode=rw", uri=True) as connection:
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        except (OSError, sqlite3.Error) as error:
            return {"status": "INIT_FAILED", "runtime_home": str(self.paths.home), "db_path": str(self.paths.db), "schema_version": None, "warnings": [type(error).__name__]}
        return {"status": "INIT_ALREADY_COMPLETE" if existed else "INIT_COMPLETE", "runtime_home": str(self.paths.home), "db_path": str(self.paths.db), "schema_version": version or SCHEMA_VERSION, "created_dirs": sorted(self.paths.directories()), "warnings": []}

    def snapshot_validate(self, path: Path) -> dict[str, object]:
        account = load_snapshot(path)
        return {"valid": True, "snapshot_id": account.snapshot_id, "as_of": account.as_of.isoformat(), "freshness": account.freshness_state.value, "sync": account.sync_state.value, "sanitized": True}

    def daily(self, snapshot_path: Path, market_fixture: Path | None = None) -> dict[str, object]:
        account = load_snapshot(snapshot_path)
        policies = load_policies(policy_directory())
        cutoff = datetime.now(account.as_of.tzinfo)
        if market_fixture:
            quotes = load_market_fixture(market_fixture)
            provenance: dict[str, object] = {"data_mode": "FIXTURE", "information_cutoff": cutoff.isoformat(), "provider_health": {ticker: {"primary": "FIXTURE", "secondary": "NOT_USED"} for ticker in quotes}, "cache": {}, "provider_conflicts": {}, "symbols_missing": {}}
        else:
            symbols = set(policies.universe.tickers) | {holding.ticker for holding in account.holdings}
            operational = OperationalMarketSnapshotService.from_runtime(self.paths).build(symbols, analysis_time=cutoff)
            quotes = operational.quotes if not operational.missing_symbols else {}
            provenance = {"data_mode": operational.data_mode, "market_snapshot_hash": operational.snapshot_hash, "information_cutoff": operational.information_cutoff.isoformat(), "provider_health": operational.provider_health, "cache": operational.cache, "provider_conflicts": operational.conflicts, "symbols_missing": operational.missing_symbols, "research_pit": "BLOCKED"}
        result = DailyClosureService(policies).run(account, quotes, cutoff=cutoff)
        result.report.update(provenance)
        persisted = persist_report(result, self.paths)
        return {**persisted.report, "report_json": str(persisted.report_json), "report_markdown": str(persisted.report_markdown)}

    def data_status(self) -> dict[str, object]:
        policies = load_policies(policy_directory())
        snapshot = OperationalMarketSnapshotService.from_runtime(self.paths).build(policies.universe.tickers, analysis_time=datetime.now().astimezone())
        return snapshot.data_status()

    def dip_scout(self, packet_path: Path) -> dict[str, object]:
        return dip_scout(ResearchPacket.model_validate_json(packet_path.read_text(encoding="utf-8")))

    def forward_status(self) -> dict[str, object]:
        ledger = ForwardLedger(self.paths.audit / "forward-evidence.json")
        return ledger.evaluate()
