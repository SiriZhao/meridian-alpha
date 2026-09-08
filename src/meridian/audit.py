"""Sanitized, idempotent SQLite audit storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meridian.schemas import DailyDecision

SCHEMA_VERSION = 3


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    decision_hash: str
    overall_status: str
    as_of: str
    created_at: str


class AuditStore:
    """Stores sanitized decisions; never accepts raw account snapshots or secrets."""

    def __init__(self, path: Path, *, persist_sensitive_account_data: bool = False) -> None:
        if persist_sensitive_account_data:
            raise ValueError("persist_sensitive_account_data must remain false by default")
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def migrate(self) -> None:
        with closing(self.connect()) as connection, connection:
            table = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
            if table:
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                if version is not None and version > SCHEMA_VERSION:
                    raise sqlite3.DatabaseError("MERIDIAN_DATABASE_NEWER_SCHEMA: upgrade Meridian before opening this database")
            for name, required in (
                ("snapshot_receipts", {"snapshot_key", "content_hash", "first_seen_at"}),
                ("run_readiness", {"run_id", "payload_json"}),
                ("paper_accounts", {"account_name", "cash", "ledger_version"}),
                ("paper_positions", {"account_name", "ticker", "quantity", "average_cost"}),
                ("paper_fills", {"fill_id", "account_name", "paper_order_id"}),
                ("paper_ledger", {"account_name", "sequence", "event_type"}),
                ("paper_daily_runs", {"account_name", "trading_date", "canonical_run_id"}),
                ("paper_nav_history", {"account_name", "trading_date", "nav"}),
            ):
                existing = connection.execute("SELECT type FROM sqlite_master WHERE name=?", (name,)).fetchone()
                if existing:
                    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({name})")}
                    if existing[0] != "table" or not required.issubset(columns):
                        raise sqlite3.DatabaseError("MERIDIAN_DATABASE_SCHEMA_COLLISION")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    decision_hash TEXT NOT NULL,
                    overall_status TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS recommendations (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    ticker TEXT NOT NULL,
                    target_weight TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    PRIMARY KEY (run_id, ticker)
                );
                CREATE TABLE IF NOT EXISTS target_portfolios (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    allocator_name TEXT NOT NULL,
                    allocator_version TEXT NOT NULL,
                    cash_weight TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS order_drafts (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    preferred_limit TEXT,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    PRIMARY KEY (run_id, ticker)
                );
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS model_metadata (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    framework_version TEXT NOT NULL,
                    PRIMARY KEY (run_id, provider, model_name)
                );
                INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
                CREATE TABLE IF NOT EXISTS snapshot_receipts (
                    snapshot_key TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    first_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_readiness (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    payload_json TEXT NOT NULL
                );
                INSERT OR IGNORE INTO schema_migrations(version) VALUES (2);
                CREATE TABLE IF NOT EXISTS paper_accounts (
                    account_name TEXT PRIMARY KEY,
                    currency TEXT NOT NULL,
                    starting_cash TEXT NOT NULL,
                    cash TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    ledger_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    benchmark_symbol TEXT NOT NULL,
                    benchmark_inception_price TEXT
                );
                CREATE TABLE IF NOT EXISTS paper_positions (
                    account_name TEXT NOT NULL REFERENCES paper_accounts(account_name),
                    ticker TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    average_cost TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_name, ticker)
                );
                CREATE TABLE IF NOT EXISTS paper_fills (
                    fill_id TEXT PRIMARY KEY,
                    account_name TEXT NOT NULL REFERENCES paper_accounts(account_name),
                    paper_order_id TEXT NOT NULL,
                    canonical_run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    reference_price TEXT NOT NULL,
                    fill_price TEXT NOT NULL,
                    slippage_bps TEXT NOT NULL,
                    fees TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    filled_at TEXT NOT NULL,
                    UNIQUE(account_name, paper_order_id)
                );
                CREATE TABLE IF NOT EXISTS paper_ledger (
                    account_name TEXT NOT NULL REFERENCES paper_accounts(account_name),
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    run_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (account_name, sequence)
                );
                CREATE TABLE IF NOT EXISTS paper_daily_runs (
                    account_name TEXT NOT NULL REFERENCES paper_accounts(account_name),
                    trading_date TEXT NOT NULL,
                    canonical_run_id TEXT NOT NULL,
                    order_intent_hash TEXT NOT NULL,
                    execution_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (account_name, trading_date)
                );
                CREATE TABLE IF NOT EXISTS paper_nav_history (
                    account_name TEXT NOT NULL REFERENCES paper_accounts(account_name),
                    trading_date TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    cash TEXT NOT NULL,
                    market_value TEXT NOT NULL,
                    nav TEXT NOT NULL,
                    daily_return TEXT,
                    cumulative_return TEXT NOT NULL,
                    drawdown TEXT NOT NULL,
                    turnover TEXT NOT NULL,
                    fees TEXT NOT NULL,
                    trade_count INTEGER NOT NULL,
                    benchmark_price TEXT,
                    benchmark_cumulative_return TEXT,
                    PRIMARY KEY (account_name, trading_date)
                );
                INSERT OR IGNORE INTO schema_migrations(version) VALUES (3);
                COMMIT;
                """
            )

    @staticmethod
    def decision_hash(decision: DailyDecision) -> str:
        return hashlib.sha256(decision.stable_json().encode("utf-8")).hexdigest()

    def write_decision(self, decision: DailyDecision) -> None:
        """Write once or accept only the byte-equivalent decision for a run id."""
        digest = self.decision_hash(decision)
        self.migrate()
        with closing(self.connect()) as connection, connection:
            existing = connection.execute(
                "SELECT decision_hash FROM runs WHERE run_id = ?", (decision.run_id,)
            ).fetchone()
            if existing is not None:
                if existing["decision_hash"] != digest:
                    raise ValueError("run_id already exists with a contradictory decision")
                return
            connection.execute(
                "INSERT INTO runs(run_id, decision_hash, overall_status, as_of) VALUES (?, ?, ?, ?)",
                (decision.run_id, digest, decision.overall_status, decision.as_of.isoformat()),
            )
            if decision.target_portfolio is not None:
                portfolio = decision.target_portfolio
                connection.execute(
                    "INSERT INTO target_portfolios VALUES (?, ?, ?, ?)",
                    (
                        decision.run_id,
                        portfolio.allocator_name,
                        portfolio.allocator_version,
                        str(portfolio.cash_weight),
                    ),
                )
                connection.executemany(
                    "INSERT INTO recommendations VALUES (?, ?, ?, ?)",
                    [
                        (
                            decision.run_id,
                            position.ticker,
                            str(position.target_weight),
                            position.rationale,
                        )
                        for position in portfolio.positions
                    ],
                )
            connection.executemany(
                "INSERT INTO order_drafts VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        decision.run_id,
                        order.ticker,
                        order.side,
                        str(order.quantity),
                        str(order.preferred_limit) if order.preferred_limit is not None else None,
                        order.status,
                        order.reason,
                    )
                    for order in decision.orders
                ],
            )
            connection.execute(
                "INSERT INTO system_events(run_id, event_type, payload_json) VALUES (?, ?, ?)",
                (
                    decision.run_id,
                    "daily_decision_recorded",
                    json.dumps(
                        {"warnings": decision.warnings, "blocked_reasons": decision.blocked_reasons}
                    ),
                ),
            )

    def write_research_outcomes(self, run_id: str, outcomes: Sequence[object]) -> None:
        """Persist only safe model metadata and status; never transcripts or secrets."""
        self.migrate()
        with closing(self.connect()) as connection, connection:
            if (
                connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                is None
            ):
                raise ValueError("cannot attach research outcomes to unknown run")
            for outcome in outcomes:
                connection.execute(
                    "INSERT OR IGNORE INTO model_metadata(run_id, provider, model_name, framework_version) VALUES (?, ?, ?, ?)",
                    (
                        run_id,
                        str(getattr(outcome, "provider", "UNKNOWN")),
                        str(getattr(outcome, "model_name", "UNKNOWN")),
                        str(getattr(outcome, "framework_version", "UNKNOWN")),
                    ),
                )
                payload = {
                    "ticker": str(getattr(outcome, "ticker", "UNKNOWN")),
                    "status": str(getattr(outcome, "status", "UNKNOWN")),
                    "framework": str(getattr(outcome, "framework", "UNKNOWN")),
                    "graph_rating": getattr(outcome, "graph_rating", None),
                    "selected_analysts": list(
                        getattr(outcome, "selected_analysts", ())
                    ),
                    "reports_present": list(getattr(outcome, "reports_present", ())),
                    "started_at": getattr(
                        getattr(outcome, "started_at", None), "isoformat", lambda: None
                    )(),
                    "completed_at": getattr(
                        getattr(outcome, "completed_at", None), "isoformat", lambda: None
                    )(),
                    "retry_count": int(getattr(outcome, "retry_count", 0)),
                    "duration_seconds": str(getattr(outcome, "duration_seconds", "UNKNOWN")),
                    "point_in_time_status": str(
                        getattr(outcome, "point_in_time_status", "UNKNOWN")
                    ),
                    "error_code": getattr(outcome, "error_code", None),
                    "token_usage": getattr(outcome, "token_usage", None),
                }
                connection.execute(
                    "INSERT INTO system_events(run_id, event_type, payload_json) VALUES (?, ?, ?)",
                    (run_id, "research_outcome", json.dumps(payload, sort_keys=True)),
                )

    def write_research_pipeline(self, run_id: str, result: Any) -> None:
        """Persist only bounded pipeline metadata; never evidence prose or credentials."""
        self.migrate()
        with closing(self.connect()) as connection, connection:
            if (
                connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                is None
            ):
                raise ValueError("cannot attach research pipeline to unknown run")
            candidate_set = result.candidate_set
            payload = {
                "mode": str(result.mode),
                "status": str(result.status),
                "synthetic": bool(result.synthetic),
                "candidates": [
                    {
                        "ticker": candidate.ticker,
                        "rank": candidate.rank,
                        "quant_score": str(candidate.quant_score),
                        "is_existing_holding": candidate.is_existing_holding,
                        "deferred_reason": candidate.deferred_reason,
                    }
                    for candidate in (*candidate_set.candidates, *candidate_set.deferred)
                ],
                "graph": [
                    {
                        "ticker": summary.ticker,
                        "status": str(summary.status),
                        "graph_rating": summary.graph_rating,
                        "provider": summary.provider,
                        "model": summary.model,
                        "framework_version": summary.framework_version,
                        "duration_seconds": str(summary.duration_seconds),
                    }
                    for summary in result.graph_summaries
                ],
                "evidence_ids": [
                    item.stable_id
                    for packet in result.evidence_packets
                    for item in packet.items
                ],
                "grounded": [
                    {
                        "ticker": outcome.ticker,
                        "status": str(outcome.status),
                        "provider": outcome.provider,
                        "model": outcome.model,
                        "error_code": outcome.error_code,
                    }
                    for outcome in result.grounded_outcomes
                ],
                "agent_signals": [
                    {
                        "ticker": signal.ticker,
                        "direction": signal.direction,
                        "conviction": str(signal.conviction),
                        "evidence_ids": [item.stable_id for item in signal.evidence],
                    }
                    for signal in result.agent_signals
                ],
                "warnings": list(result.warnings),
            }
            connection.execute(
                "INSERT INTO system_events(run_id, event_type, payload_json) VALUES (?, ?, ?)",
                (run_id, "research_pipeline", json.dumps(payload, sort_keys=True)),
            )

    def list_runs(self) -> list[StoredRun]:
        self.migrate()
        with closing(self.connect()) as connection, connection:
            return [
                StoredRun(**dict(row))
                for row in connection.execute("SELECT * FROM runs ORDER BY created_at DESC")
            ]

    def get_decision_summary(self, run_id: str) -> dict[str, object] | None:
        self.migrate()
        with closing(self.connect()) as connection, connection:
            run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                return None
            return {
                "run": dict(run),
                "orders": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM order_drafts WHERE run_id = ?", (run_id,)
                    )
                ],
                "recommendations": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM recommendations WHERE run_id = ?", (run_id,)
                    )
                ],
            }


    def snapshot_novelty(self, snapshot_key: str, content_hash: str, *, seen_at: str | None = None) -> str:
        """Check or atomically claim hashes, never raw account facts.

        A failed run may leave a receipt: conservative replay protection requires
        a new snapshot rather than silently reusing input after a crash.
        """
        if not self.path.exists() and seen_at is None:
            return "NEW"
        with closing(self.connect()) as connection, connection:
            if seen_at is not None:
                connection.execute("BEGIN IMMEDIATE")
            table = connection.execute("SELECT name FROM sqlite_master WHERE name='snapshot_receipts'").fetchone()
            if not table:
                if seen_at is None:
                    return "NEW"
                raise sqlite3.DatabaseError("SNAPSHOT_RECEIPTS_MIGRATION_REQUIRED")
            previous = connection.execute("SELECT content_hash FROM snapshot_receipts WHERE snapshot_key=?", (snapshot_key,)).fetchone()
            if previous:
                return "REPLAYED" if previous[0] == content_hash else "CONFLICT"
            if connection.execute("SELECT 1 FROM snapshot_receipts WHERE content_hash=?", (content_hash,)).fetchone():
                return "REPLAYED"
            if seen_at is not None:
                connection.execute("INSERT INTO snapshot_receipts VALUES (?, ?, ?)", (snapshot_key, content_hash, seen_at))
            return "NEW"

    def write_readiness(self, run_id: str, as_of: str, status: str, payload: dict[str, object]) -> None:
        """Append immutable diagnostics to the same run, including rejected input."""
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT payload_json FROM run_readiness WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise ValueError("READINESS_RUN_CONFLICT")
                return
            connection.execute("INSERT OR IGNORE INTO runs(run_id, decision_hash, overall_status, as_of) VALUES (?, ?, ?, ?)", (run_id, digest, status, as_of))
            connection.execute("INSERT INTO run_readiness VALUES (?, ?)", (run_id, encoded))
