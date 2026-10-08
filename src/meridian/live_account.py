"""Read-only paper inspection: no schema creation, migrations or account setup."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from meridian.audit import SCHEMA_VERSION, AuditStore
from meridian.paper import DEFAULT_ACCOUNT, PaperLedger, PaperSettings
from meridian.readonly_storage import ReadOnlyStorageRefusal, connect_read_only


class ReadOnlyAuditStore(AuditStore):
    def connect(self) -> sqlite3.Connection:
        connection = connect_read_only(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def migrate(self) -> None:
        with closing(self.connect()) as connection:
            version = connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
            if version != SCHEMA_VERSION:
                raise sqlite3.DatabaseError('PAPER_SCHEMA_REVIEW_REQUIRED_NO_MIGRATION')


def read_only_ledger(path: Path, settings: PaperSettings) -> PaperLedger:
    if not path.is_file():
        raise ValueError('PAPER_DATABASE_NOT_FOUND_NO_AUTO_INITIALIZATION')
    return PaperLedger(ReadOnlyAuditStore(path), settings)


def inspect_paper(path: Path, settings: PaperSettings, now: datetime) -> dict[str, Any]:
    try:
        ledger = read_only_ledger(path, settings)
        status = ledger.status(DEFAULT_ACCOUNT)
        if not status.get('found'):
            return {**status, 'ready': False, 'ledger_written': False}
        state = ledger.state(DEFAULT_ACCOUNT)
        if state is None or state.cash < 0 or any(p.quantity < 0 for p in state.positions):
            raise ValueError('PAPER_LEDGER_INVALID')
        with closing(ledger.store.connect()) as connection:
            rows = connection.execute(
                'SELECT trading_date, canonical_run_id, execution_status FROM paper_daily_runs '
                'WHERE account_name=? ORDER BY trading_date DESC LIMIT 5', (DEFAULT_ACCOUNT,)
            ).fetchall()
        return {**status, 'ready': True, 'observed_at': now.isoformat(),
                'nav_semantics': 'BOOK_COST_BASIS; latest_performance is a separately dated historical mark',
                'pending_partial_state': 'NO_BROKER_PENDING_ORDER_SOURCE; paper ownership shown separately',
                'recent_ownership': [dict(row) for row in rows], 'ledger_written': False,
                'real_schwab_account': False, 'sector_metadata': 'NOT_IN_LEDGER',
                'account_freshness': 'READ_TIME_LOCAL_LEDGER_NOT_FRESH_BROKER_CONFIRMATION'}
    except (ValueError, sqlite3.Error, OSError) as error:
        code = str(error) if isinstance(error, (ValueError, ReadOnlyStorageRefusal)) else 'PAPER_STORAGE_OR_SCHEMA_UNAVAILABLE'
        return {'ready': False, 'status': code, 'account': DEFAULT_ACCOUNT, 'ledger_written': False}
