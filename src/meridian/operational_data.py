"""Bounded operational market-data plane, separate from PIT certification.

Operational observations support today's non-executable analysis context only.
They are never evidence of certified historical research or execution quotes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from uuid import uuid4

from meridian.provider_resilience import FailureCategory, ProviderHealthStore, classify_failure
from meridian.quotes import (
    QuoteObservation,
    QuoteProviderError,
    QuoteProviderMalformed,
    QuoteProviderTimeout,
)
from meridian.trading_calendar import (
    NEW_YORK,
    is_trading_session,
    latest_completed_session,
    session_close,
    session_context,
)


class OperationalReadiness(StrEnum):
    OPERATIONAL_READY = "OPERATIONAL_READY"
    OPERATIONAL_DEGRADED = "OPERATIONAL_DEGRADED"
    RESEARCH_PARTIAL = "RESEARCH_PARTIAL"
    RESEARCH_BLOCKED = "RESEARCH_BLOCKED"
    CERTIFIED = "CERTIFIED"


class OperationalProviderStatus(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    INVALID_RESPONSE = "INVALID_RESPONSE"


@dataclass(frozen=True)
class FreshnessPolicy:
    quote_max_age_seconds: int = 900
    daily_bar_max_age_sessions: int = 1
    account_max_age_seconds: int = 900
    research_max_age_seconds: int = 86_400
    event_max_age_seconds: int = 86_400

    def __post_init__(self) -> None:
        if any(value < 0 for value in asdict(self).values()):
            raise ValueError("freshness thresholds must be non-negative")

    def quote_status(self, observation: OperationalQuote, *, as_of: datetime) -> OperationalProviderStatus:
        _aware(as_of, "as_of")
        if observation.timestamp > as_of or observation.received_at > as_of:
            return OperationalProviderStatus.INVALID_RESPONSE
        if observation.available_at is not None and observation.available_at > as_of:
            return OperationalProviderStatus.INVALID_RESPONSE
        if observation.quality is not OperationalProviderStatus.OK:
            return observation.quality
        if observation.session == "OPEN" and session_context(observation.timestamp) != "REGULAR":
            return OperationalProviderStatus.INVALID_RESPONSE
        age = (as_of - observation.timestamp).total_seconds()
        if age > self.quote_max_age_seconds:
            return OperationalProviderStatus.STALE
        # A recent timestamp during a scheduled closure is not a fresh trade.
        # Prior-session closes remain diagnostic context, never a stale override.
        if session_context(observation.timestamp) == "CLOSED":
            return OperationalProviderStatus.INVALID_RESPONSE
        if session_context(as_of) == "REGULAR" and session_context(observation.timestamp) != "REGULAR":
            return OperationalProviderStatus.INVALID_RESPONSE
        return OperationalProviderStatus.OK

    def research_quote_eligible(self, observation: OperationalQuote, *, as_of: datetime) -> bool:
        """Accept only the latest completed-session close for research context.

        The same observation remains stale and unusable for execution, sizing,
        and limit pricing.
        """
        _aware(as_of, "as_of")
        if observation.timestamp > as_of or observation.received_at > as_of:
            return False
        if session_context(as_of) == "REGULAR":
            return False
        completed = latest_completed_session(as_of)
        observed_session = observation.timestamp.astimezone(NEW_YORK).date()
        return (
            observed_session == completed
            and abs(
                (observation.timestamp - session_close(completed)).total_seconds()
            )
            <= self.quote_max_age_seconds
        )

    def describe(self, observation: OperationalQuote, *, as_of: datetime) -> dict[str, object]:
        status = self.quote_status(observation, as_of=as_of)
        context = session_context(as_of)
        completed = latest_completed_session(as_of)
        closing_context = self.research_quote_eligible(observation, as_of=as_of)
        return {
            "symbol": observation.symbol, "provider": observation.provider,
            "source_timestamp": observation.timestamp.isoformat(),
            "received_at": observation.received_at.isoformat(),
            "analysis_cutoff": as_of.isoformat(),
            "age_seconds": (as_of - observation.timestamp).total_seconds(),
            "session": context, "provider_session": observation.session,
            "latest_completed_session": completed.isoformat(),
            "status": status.value,
            "research_context": "LAST_COMPLETED_SESSION_ONLY" if closing_context and status is OperationalProviderStatus.STALE else status.value,
            "error_category": "DATA_QUALITY" if status is not OperationalProviderStatus.OK else None,
            "quote_kind": "PUBLIC_RESEARCH_QUOTE", "quote_certification_status": "BLOCKED",
            "provenance": dict(observation.provenance or {}),
        }

    def daily_bar_is_current(self, bar_session: date, *, as_of: datetime) -> bool:
        completed = latest_completed_session(as_of)
        if bar_session > completed or not is_trading_session(bar_session):
            return False
        age = 0
        candidate = completed
        while candidate > bar_session:
            if is_trading_session(candidate):
                age += 1
                if age > self.daily_bar_max_age_sessions:
                    return False
            candidate -= timedelta(days=1)
        return True


@dataclass(frozen=True)
class OperationalQuote:
    symbol: str
    price: Decimal
    timestamp: datetime
    received_at: datetime
    provider: str
    source_type: str
    currency: str
    session: str
    quality: OperationalProviderStatus = OperationalProviderStatus.OK
    provenance: Mapping[str, str] | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.price.is_finite() or self.price <= 0:
            raise ValueError("operational quote requires a positive symbol and price")
        _aware(self.timestamp, "timestamp")
        _aware(self.received_at, "received_at")
        if self.timestamp > self.received_at:
            raise ValueError("operational quote timestamp is after received_at")
        if self.available_at is not None:
            _aware(self.available_at, "available_at")
            if not self.timestamp <= self.available_at <= self.received_at:
                raise ValueError("operational quote availability is inconsistent")
        if len(self.currency) != 3:
            raise ValueError("operational quote currency must be ISO-4217")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_shadow_quote(cls, quote: QuoteObservation) -> OperationalQuote:
        if quote.last is None:
            raise ValueError("operational quote requires provider last price")
        if quote.available_at > quote.retrieved_at:
            raise ValueError("MARKET_AVAILABILITY_AFTER_RECEIPT")
        quality = OperationalProviderStatus.INVALID_RESPONSE if quote.quality_status.value in {"INVALID", "FUTURE", "MARKET_DATA_CONFLICT"} else OperationalProviderStatus.STALE if quote.quality_status.value == "STALE" else OperationalProviderStatus.OK
        return cls(symbol=quote.canonical_symbol, price=quote.last, timestamp=quote.observed_at, received_at=quote.retrieved_at, available_at=quote.available_at, provider=quote.provider, source_type="PUBLIC_SHADOW_LAST", currency=quote.currency, session=quote.market_status.value, quality=quality, provenance={"provider_symbol": quote.provider_symbol, "source": quote.source, "shadow_only": "true"})


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class OperationalQuoteProvider(Protocol):
    provider_name: str

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation: ...


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    status: OperationalProviderStatus
    detail: str
    quote: OperationalQuote | None = None
    attempted_at: datetime | None = None
    completed_at: datetime | None = None
    raw_category: str | None = None
    normalized_category: FailureCategory | None = None

    @property
    def latency_ms(self) -> int | None:
        return max(0, round((self.completed_at - self.attempted_at).total_seconds() * 1000)) if self.completed_at and self.attempted_at else None


@dataclass(frozen=True)
class OperationalSnapshot:
    analysis_time: datetime
    information_cutoff: datetime
    primary: ProviderResult
    secondary: ProviderResult
    selected: OperationalQuote | None
    readiness: OperationalReadiness
    research_readiness: OperationalReadiness
    conflict_percent: Decimal | None
    cache_hit: bool
    cache_status: str = "NOT_CONFIGURED"
    selected_lane: str = "NONE"
    data_quality_mode: str = "DATA_DEGRADED"
    provider_health: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _aware(self.analysis_time, "analysis_time")
        _aware(self.information_cutoff, "information_cutoff")
        if self.information_cutoff > self.analysis_time:
            raise ValueError("information cutoff is after analysis time")
        if self.selected is not None and self.selected.timestamp > self.information_cutoff:
            raise ValueError("operational snapshot contains future data")


class OperationalCache:
    """Atomic, provenance-preserving cache that quarantines corrupt inputs."""

    schema_version = "operational-quote.v1"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, symbol: str, provider: str) -> Path:
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,15}", symbol) or not re.fullmatch(r"[A-Za-z0-9._\-]{1,128}", provider):
            raise ValueError("OPERATIONAL_CACHE_IDENTITY_INVALID")
        safe = "".join(char for char in f"{provider}-{symbol}" if char.isalnum() or char in "-_")
        identity = hashlib.sha256(json.dumps([provider, symbol], separators=(",", ":")).encode()).hexdigest()[:16]
        return self.directory / f"{safe}-{identity}.json"

    def load(self, symbol: str, provider: str) -> OperationalQuote | None:
        path = self._path(symbol, provider)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schema_version") != self.schema_version:
                raise ValueError("invalid cache envelope")
            body = raw.get("quote")
            declared = raw.get("content_hash")
            if not isinstance(body, dict) or not isinstance(declared, str):
                raise ValueError("invalid cache fields")
            actual = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if actual != declared:
                raise ValueError("cache hash mismatch")
            quote = OperationalQuote(symbol=str(body["symbol"]), price=Decimal(str(body["price"])), timestamp=datetime.fromisoformat(str(body["timestamp"])), received_at=datetime.fromisoformat(str(body["received_at"])), available_at=datetime.fromisoformat(str(body["available_at"])) if body.get("available_at") else None, provider=str(body["provider"]), source_type=str(body["source_type"]), currency=str(body["currency"]), session=str(body["session"]), quality=OperationalProviderStatus(str(body["quality"])), provenance=body.get("provenance"))
            if quote.symbol != symbol or raw.get("key_provider", quote.provider) != provider:
                raise ValueError("cache identity mismatch")
            return quote
        except (OSError, ValueError, KeyError, TypeError, InvalidOperation):
            try:
                path.replace(path.with_suffix(path.suffix + "." + uuid4().hex + ".corrupt"))
            except OSError:
                pass
            return None

    def store(self, quote: OperationalQuote, *, provider: str | None = None) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(quote.symbol, provider or quote.provider)
        body = asdict(quote)
        body["price"] = str(quote.price)
        body["timestamp"] = quote.timestamp.isoformat()
        body["received_at"] = quote.received_at.isoformat()
        body["available_at"] = quote.available_at.isoformat() if quote.available_at else None
        body["quality"] = quote.quality.value
        payload = {"schema_version": self.schema_version, "key_provider": provider or quote.provider, "quote": body, "content_hash": hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            temporary.replace(path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class OperationalRefreshService:
    """One bounded refresh boundary; downstream code receives only its snapshot."""

    def __init__(self, primary: OperationalQuoteProvider, secondary: OperationalQuoteProvider | None = None, *, policy: FreshnessPolicy | None = None, cache: OperationalCache | None = None, discrepancy_tolerance_percent: Decimal = Decimal("0.02")) -> None:
        if discrepancy_tolerance_percent < 0:
            raise ValueError("discrepancy tolerance must be non-negative")
        self.primary, self.secondary, self.policy, self.cache, self.discrepancy_tolerance_percent = primary, secondary, policy or FreshnessPolicy(), cache, discrepancy_tolerance_percent

    def refresh(self, symbol: str, *, analysis_time: datetime, live: bool = False) -> OperationalSnapshot:
        _aware(analysis_time, "analysis_time")
        primary = self._fetch(self.primary, symbol, analysis_time, live=live)
        secondary = self._fetch(self.secondary, symbol, analysis_time, live=live) if self.secondary else ProviderResult("trusted-web-evidence", OperationalProviderStatus.UNAVAILABLE, "OUTER_ASTRA_VALIDATION_REQUIRED")
        if live:
            analysis_time = datetime.now(UTC)
            def revalidate(result: ProviderResult) -> ProviderResult:
                if result.quote is None:
                    return result
                status = self.policy.quote_status(result.quote, as_of=analysis_time)
                category = FailureCategory.STALE_DATA if status is OperationalProviderStatus.STALE else result.normalized_category or FailureCategory.INVALID_RESPONSE if status is not OperationalProviderStatus.OK else None
                return replace(result, status=status, normalized_category=category)
            primary, secondary = revalidate(primary), revalidate(secondary)
        selected = primary.quote if primary.status is OperationalProviderStatus.OK else secondary.quote if secondary.status is OperationalProviderStatus.OK else None
        selected_lane = "PRIMARY" if selected is not None and selected is primary.quote else "FALLBACK" if selected is not None and selected is secondary.quote else "NONE"
        cache_hit = False
        cache_status = "NOT_CONFIGURED" if self.cache is None else "NOT_USED"
        if selected is None and self.cache is not None:
            cache_status = "MISS"
            for provider in (self.primary, self.secondary):
                if provider is None:
                    continue
                cached = self.cache.load(symbol, provider.provider_name)
                if cached is not None and cached.symbol == symbol and self.policy.quote_status(cached, as_of=analysis_time) is OperationalProviderStatus.OK:
                    selected, cache_hit = cached, True
                    selected_lane, cache_status = "CACHE", "HIT"
                    break
        conflict = None
        if primary.status is OperationalProviderStatus.OK and secondary.status is OperationalProviderStatus.OK and primary.quote is not None and secondary.quote is not None:
            conflict = abs(primary.quote.price - secondary.quote.price) / primary.quote.price
        conflict_block = conflict is not None and conflict > self.discrepancy_tolerance_percent
        if selected is not None and self.cache is not None and not cache_hit and not conflict_block:
            try:
                self.cache.store(selected, provider=primary.provider if selected is primary.quote else secondary.provider)
                cache_status = "WRITE_OK"
            except OSError:
                # Cache is an availability lane, never authority. A cache ACL/EFS
                # failure must not discard an already-validated provider quote.
                cache_status = "WRITE_FAILED"
        readiness = OperationalReadiness.OPERATIONAL_READY if selected is not None and self.policy.quote_status(selected, as_of=analysis_time) is OperationalProviderStatus.OK and not conflict_block else OperationalReadiness.OPERATIONAL_DEGRADED
        provider_degraded = primary.status is not OperationalProviderStatus.OK or secondary.status is not OperationalProviderStatus.OK
        data_quality_mode = "DATA_DEGRADED" if provider_degraded or cache_status in {"HIT", "MISS", "WRITE_FAILED"} or conflict_block else "NORMAL"
        provider_health: dict[str, object] = {}
        if self.cache is not None and isinstance(getattr(self.cache, "directory", None), Path):
            for result in (primary, secondary):
                if result.completed_at is None:
                    continue
                try:
                    provider_health[result.provider] = ProviderHealthStore(self.cache.directory / "provider-health.sqlite3").record(provider=result.provider, symbol=symbol, channel="LIVE_QUOTE" if live else "REPLAY_QUOTE", category=result.normalized_category.value if result.normalized_category else None, latency_ms=result.latency_ms or 0, completed_at=result.completed_at, fallback=selected_lane in {"FALLBACK", "CACHE"})
                except (OSError, sqlite3.Error):
                    provider_health[result.provider] = {"status": "TELEMETRY_UNAVAILABLE", "routing_effect": "NONE_OBSERVATIONAL_ONLY"}
        return OperationalSnapshot(analysis_time=analysis_time, information_cutoff=analysis_time, primary=primary, secondary=secondary, selected=selected, readiness=readiness, research_readiness=OperationalReadiness.RESEARCH_BLOCKED, conflict_percent=conflict, cache_hit=cache_hit, cache_status=cache_status, selected_lane=selected_lane, data_quality_mode=data_quality_mode, provider_health=provider_health)

    def _fetch(self, provider: OperationalQuoteProvider, symbol: str, as_of: datetime, *, live: bool = False) -> ProviderResult:
        started = datetime.now(UTC)
        try:
            quote = OperationalQuote.from_shadow_quote(provider.get_quote(symbol, as_of=None if live else as_of))
            if quote.symbol != symbol:
                raise ValueError("MARKET_SYMBOL_MISMATCH")
            status = self.policy.quote_status(quote, as_of=max(as_of, quote.received_at) if live else as_of)
            category = FailureCategory.STALE_DATA if status is OperationalProviderStatus.STALE else FailureCategory.SESSION_MISMATCH if quote.session == "OPEN" and session_context(quote.timestamp) != "REGULAR" else FailureCategory.INVALID_RESPONSE if status is not OperationalProviderStatus.OK else None
            return ProviderResult(provider.provider_name, status, "public operational observation; not PIT certified", quote, started, datetime.now(UTC), status.value if category else None, category)
        except QuoteProviderTimeout:
            return ProviderResult(provider.provider_name, OperationalProviderStatus.UNAVAILABLE, "timeout", attempted_at=started, completed_at=datetime.now(UTC), raw_category="PROVIDER_TIMEOUT", normalized_category=FailureCategory.TIMEOUT)
        except (QuoteProviderMalformed, ValueError, TypeError, KeyError, AttributeError, IndexError, ArithmeticError) as error:
            return ProviderResult(provider.provider_name, OperationalProviderStatus.INVALID_RESPONSE, "invalid_response", attempted_at=started, completed_at=datetime.now(UTC), raw_category=type(error).__name__, normalized_category=classify_failure(error))
        except QuoteProviderError as error:
            cause = error.__cause__
            detail = f"http_{cause.code}" if isinstance(cause, HTTPError) else "timeout" if isinstance(cause, TimeoutError) else "network_unavailable" if isinstance(cause, URLError) else "provider_error"
            return ProviderResult(provider.provider_name, OperationalProviderStatus.UNAVAILABLE, detail, attempted_at=started, completed_at=datetime.now(UTC), raw_category=error.code, normalized_category=classify_failure(error))
        except OSError as error:
            return ProviderResult(provider.provider_name, OperationalProviderStatus.UNAVAILABLE, "network_unavailable", attempted_at=started, completed_at=datetime.now(UTC), raw_category=type(error).__name__, normalized_category=classify_failure(error))


def data_status(snapshot: OperationalSnapshot | None = None) -> dict[str, object]:
    """Human and machine readable separation of today's data from research PIT."""
    if snapshot is None:
        return {"market_calendar": "OK", "primary_price": "UNAVAILABLE", "secondary_price": "UNAVAILABLE", "latest_quote": "UNAVAILABLE", "latest_daily_bar": "UNKNOWN", "account_snapshot": "EXTERNAL_INPUT_REQUIRED", "sec_pit_research": "PARTIAL", "historical_universe": "BLOCKED", "operational": OperationalReadiness.OPERATIONAL_DEGRADED.value, "research": OperationalReadiness.RESEARCH_BLOCKED.value, "certification": "OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH"}
    return {"market_calendar": "OK", "primary_price": snapshot.primary.status.value, "secondary_price": snapshot.secondary.status.value, "latest_quote": "FRESH" if snapshot.readiness is OperationalReadiness.OPERATIONAL_READY else "STALE_OR_UNAVAILABLE", "latest_daily_bar": "UNKNOWN", "account_snapshot": "EXTERNAL_INPUT_REQUIRED", "sec_pit_research": "PARTIAL", "historical_universe": "BLOCKED", "operational": snapshot.readiness.value, "data_quality_mode": snapshot.data_quality_mode, "selected_lane": snapshot.selected_lane, "research": snapshot.research_readiness.value, "provider_conflict_percent": str(snapshot.conflict_percent) if snapshot.conflict_percent is not None else None, "information_cutoff": snapshot.information_cutoff.isoformat(), "cache_hit": snapshot.cache_hit, "cache_status": snapshot.cache_status, "certification": "OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH"}
