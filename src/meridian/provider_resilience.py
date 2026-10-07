"""Deterministic public-data failures and bounded, observational provider health.

Health never changes routing or grants execution authority. Only safe categories,
timings and symbol identifiers are retained, never exception text or responses.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.error import HTTPError, URLError


class FailureCategory(StrEnum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    HTTP_ERROR = "HTTP_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    EMPTY_DATA = "EMPTY_DATA"
    STALE_DATA = "STALE_DATA"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    UNKNOWN = "UNKNOWN"


def classify_failure(error: Exception) -> FailureCategory:
    """Classify types/codes, including wrapped transport errors, without prose."""
    cause = error.__cause__
    code = str(getattr(error, "code", ""))
    for category in FailureCategory:
        if code == category.value or code.endswith("_" + category.value):
            return category
    if isinstance(error, HTTPError):
        return FailureCategory.RATE_LIMIT if error.code == 429 else FailureCategory.SYMBOL_NOT_FOUND if error.code == 404 else FailureCategory.HTTP_ERROR
    if isinstance(error, TimeoutError) or "TIMEOUT" in (str(getattr(error, "code", "")) + type(error).__name__.upper()):
        return FailureCategory.TIMEOUT
    if isinstance(cause, Exception):
        nested = classify_failure(cause)
        if nested is not FailureCategory.UNKNOWN:
            return nested
    if isinstance(error, URLError):
        return FailureCategory.TIMEOUT if isinstance(error.reason, TimeoutError) else FailureCategory.NETWORK_FAILURE
    if isinstance(error, (KeyError, TypeError, AttributeError, IndexError)):
        return FailureCategory.SCHEMA_DRIFT
    if isinstance(error, (ValueError, ArithmeticError)) or "MALFORMED" in (str(getattr(error, "code", "")) + type(error).__name__.upper()):
        return FailureCategory.INVALID_RESPONSE
    if isinstance(error, OSError):
        return FailureCategory.NETWORK_FAILURE
    if "PROVIDER" in (str(getattr(error, "code", "")) + type(error).__name__.upper()):
        return FailureCategory.PROVIDER_FAILURE
    return FailureCategory.UNKNOWN


class ProviderHealthStore:
    """Transactional rolling observations; at most 256 attempts per provider/lane."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, *, provider: str, symbol: str, channel: str, category: str | None,
               latency_ms: int, completed_at: datetime, fallback: bool) -> dict[str, object]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=2)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, provider TEXT, symbol TEXT, channel TEXT, category TEXT, latency INTEGER, completed TEXT, fallback INTEGER)")
            connection.execute("INSERT INTO attempts(provider,symbol,channel,category,latency,completed,fallback) VALUES(?,?,?,?,?,?,?)",
                               (provider, symbol, channel, category, latency_ms, completed_at.isoformat(), int(fallback)))
            connection.execute("DELETE FROM attempts WHERE provider=? AND channel=? AND id NOT IN (SELECT id FROM attempts WHERE provider=? AND channel=? ORDER BY id DESC LIMIT 256)", (provider, channel, provider, channel))
            rows = connection.execute("SELECT symbol,category,latency,completed,fallback FROM attempts WHERE provider=? AND channel=? ORDER BY id DESC LIMIT 32", (provider, channel)).fetchall()
        consecutive = 0
        for row in rows:
            if row[1] is None:
                break
            consecutive += 1
        failures = [row for row in rows if row[1] is not None]
        symbols = sorted({row[0] for row in failures})
        recent = rows[:8]
        older = rows[8:16]
        return {"status": "UNHEALTHY" if consecutive >= 3 else "DEGRADED" if failures else "HEALTHY",
                "provider": provider, "channel": channel, "window_attempts": len(rows),
                "consecutive_failures": consecutive, "recent_successes": len(rows) - len(failures),
                "recent_failures": len(failures), "failure_types": dict(Counter(row[1] for row in failures)),
                "failure_symbols": symbols, "failure_scope": "MULTI_SYMBOL_OBSERVED" if len(symbols) > 1 else "SYMBOL_OBSERVED" if symbols else "NONE",
                "last_success": next((row[3] for row in rows if row[1] is None), None),
                "last_failure": next((row[3] for row in rows if row[1] is not None), None),
                "fallback_count": sum(row[4] for row in rows),
                "recent_mean_latency_ms": round(sum(row[2] for row in recent) / len(recent)),
                "prior_mean_latency_ms": round(sum(row[2] for row in older) / len(older)) if older else None,
                "routing_effect": "NONE_OBSERVATIONAL_ONLY", "broker_submission": "DISABLED"}
