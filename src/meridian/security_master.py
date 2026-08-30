"""Provider-independent Security Master contracts.

The security master is deliberately small and conservative.  It is the only
place where an external provider symbol may be translated to a Meridian
identity; unknown or conflicting identities are never silently guessed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from meridian.schemas import StableModel


class AssetType(StrEnum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    INDEX = "INDEX"


class SecurityCertificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    DEVELOPMENT_VERIFIED = "DEVELOPMENT_VERIFIED"
    AUTHORITATIVE_VERIFIED = "AUTHORITATIVE_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class SecurityIdentityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    SECURITY_IDENTITY_UNAVAILABLE = "SECURITY_IDENTITY_UNAVAILABLE"
    CONFLICTING = "CONFLICTING"


class IdentifierProvenance(StableModel):
    source: str = Field(min_length=1, max_length=256)
    identifier: str = Field(min_length=1, max_length=256)
    observed_at: datetime
    retrieved_at: datetime | None = None


class SymbolProvenance(StableModel):
    provider: str = Field(min_length=1, max_length=128)
    provider_symbol: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    retrieved_at: datetime | None = None


class SecurityMasterRecord(StableModel):
    canonical_asset_id: str = Field(min_length=1, max_length=128)
    canonical_symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    asset_type: AssetType
    primary_exchange: str = Field(min_length=1, max_length=64)
    trading_calendar: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    timezone: str = Field(min_length=1, max_length=64)
    country: str = Field(min_length=2, max_length=3)
    active_from: datetime | None = None
    active_to: datetime | None = None
    identifier_provenance: tuple[IdentifierProvenance, ...] = ()
    symbol_provenance: tuple[SymbolProvenance, ...] = ()
    last_verified_at: datetime
    certification_status: SecurityCertificationStatus

    @model_validator(mode="after")
    def validate_record(self) -> SecurityMasterRecord:
        if self.active_from is not None and self.active_to is not None:
            if self.active_to < self.active_from:
                raise ValueError("active_to must not precede active_from")
        if not self.provider_symbols:
            raise ValueError("at least one provider symbol is required")
        return self


class SecurityMasterConflict(StableModel):
    canonical_symbol: str
    conflicting_fields: tuple[str, ...]
    source_a: str
    source_b: str
    observed_at_a: datetime
    observed_at_b: datetime
    resolution: str | None = None


class SecurityIdentityUnavailable(ValueError):
    """Raised when no verified Meridian identity can be established."""

    code = SecurityIdentityStatus.SECURITY_IDENTITY_UNAVAILABLE.value


_DEFAULT_RECORDS = (
    SecurityMasterRecord(
        canonical_asset_id="US-EQ-AAPL",
        canonical_symbol="AAPL",
        provider_symbols={"stooq": "aapl.us", "yahoo": "AAPL"},
        asset_type=AssetType.EQUITY,
        primary_exchange="NASDAQ",
        trading_calendar="US_EQUITY",
        currency="USD",
        timezone="America/New_York",
        country="US",
        identifier_provenance=(IdentifierProvenance(source="meridian-fixture", identifier="AAPL", observed_at=datetime(2026, 1, 1, tzinfo=UTC)),),
        symbol_provenance=(),
        last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-EQ-MSFT", canonical_symbol="MSFT",
        provider_symbols={"stooq": "msft.us", "yahoo": "MSFT"}, asset_type=AssetType.EQUITY,
        primary_exchange="NASDAQ", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-EQ-NVDA", canonical_symbol="NVDA",
        provider_symbols={"stooq": "nvda.us", "yahoo": "NVDA"}, asset_type=AssetType.EQUITY,
        primary_exchange="NASDAQ", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-EQ-META", canonical_symbol="META",
        provider_symbols={"stooq": "meta.us", "yahoo": "META"}, asset_type=AssetType.EQUITY,
        primary_exchange="NASDAQ", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-EQ-GOOGL", canonical_symbol="GOOGL",
        provider_symbols={"stooq": "googl.us", "yahoo": "GOOGL"}, asset_type=AssetType.EQUITY,
        primary_exchange="NASDAQ", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-ETF-SPY", canonical_symbol="SPY",
        provider_symbols={"stooq": "spy.us", "yahoo": "SPY"}, asset_type=AssetType.ETF,
        primary_exchange="NYSEARCA", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-ETF-QQQ", canonical_symbol="QQQ",
        provider_symbols={"stooq": "qqq.us", "yahoo": "QQQ"}, asset_type=AssetType.ETF,
        primary_exchange="NASDAQ", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-ETF-SGOV", canonical_symbol="SGOV",
        provider_symbols={"stooq": "sgov.us", "yahoo": "SGOV"}, asset_type=AssetType.ETF,
        primary_exchange="NYSEARCA", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-ETF-GLD", canonical_symbol="GLD",
        provider_symbols={"stooq": "gld.us", "yahoo": "GLD"}, asset_type=AssetType.ETF,
        primary_exchange="NYSEARCA", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-ETF-TLT", canonical_symbol="TLT",
        provider_symbols={"stooq": "tlt.us", "yahoo": "TLT"}, asset_type=AssetType.ETF,
        primary_exchange="NASDAQ", trading_calendar="US_EQUITY", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
    SecurityMasterRecord(
        canonical_asset_id="US-INDEX-VIX", canonical_symbol="VIX",
        provider_symbols={"stooq": "^vix", "yahoo": "^VIX"}, asset_type=AssetType.INDEX,
        primary_exchange="CBOE", trading_calendar="CBOE_VIX", currency="USD",
        timezone="America/New_York", country="US", last_verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        certification_status=SecurityCertificationStatus.DEVELOPMENT_VERIFIED,
    ),
)


class SecurityMaster:
    """In-memory, deterministic registry suitable for an offline foundation."""

    def __init__(self, records: tuple[SecurityMasterRecord, ...] = _DEFAULT_RECORDS):
        self._records = {record.canonical_symbol: record for record in records}
        self._aliases = {"^VIX": "VIX", "VIX": "VIX"}
        self.conflicts: list[SecurityMasterConflict] = []

    def resolve(self, symbol: str) -> SecurityMasterRecord:
        key = symbol.strip().upper()
        canonical = self._aliases.get(key, key)
        record = self._records.get(canonical)
        if record is None or record.certification_status not in {SecurityCertificationStatus.VERIFIED, SecurityCertificationStatus.DEVELOPMENT_VERIFIED, SecurityCertificationStatus.AUTHORITATIVE_VERIFIED}:
            raise SecurityIdentityUnavailable(f"{SecurityIdentityStatus.SECURITY_IDENTITY_UNAVAILABLE.value}:{symbol}")
        return record

    def resolve_authoritative(self, symbol: str) -> SecurityMasterRecord:
        """Resolve only an explicitly authoritative, supervised identity."""
        record = self.resolve(symbol)
        if record.certification_status is not SecurityCertificationStatus.AUTHORITATIVE_VERIFIED:
            raise SecurityIdentityUnavailable(
                f"{SecurityIdentityStatus.SECURITY_IDENTITY_UNAVAILABLE.value}:authoritative-provenance-required:{symbol}"
            )
        return record

    def lookup(self, symbol: str) -> SecurityMasterRecord | None:
        try:
            return self.resolve(symbol)
        except SecurityIdentityUnavailable:
            return None

    def provider_symbol(self, symbol: str, provider: str) -> str:
        record = self.resolve(symbol)
        value = record.provider_symbols.get(provider)
        if not value:
            raise SecurityIdentityUnavailable(
                f"{SecurityIdentityStatus.SECURITY_IDENTITY_UNAVAILABLE.value}:no-symbol:{provider}:{symbol}"
            )
        return value

    def register(self, record: SecurityMasterRecord, *, source: str = "unknown", observed_at: datetime | None = None) -> None:
        """Add a record or mark existing identity CONFLICTING on disagreement."""
        existing = self._records.get(record.canonical_symbol)
        if existing is None:
            self._records[record.canonical_symbol] = record
            return
        fields = tuple(
            field for field in ("canonical_asset_id", "provider_symbols", "asset_type", "primary_exchange", "trading_calendar", "currency", "timezone", "country")
            if getattr(existing, field) != getattr(record, field)
        )
        if not fields:
            return
        observed = observed_at or record.last_verified_at
        self.register_conflict(SecurityMasterConflict(
            canonical_symbol=record.canonical_symbol,
            conflicting_fields=fields,
            source_a=source,
            source_b="existing",
            observed_at_a=observed,
            observed_at_b=existing.last_verified_at,
        ))
    def register_conflict(self, conflict: SecurityMasterConflict) -> None:
        self.conflicts.append(conflict)
        record = self._records.get(conflict.canonical_symbol)
        if record is not None:
            self._records[record.canonical_symbol] = record.model_copy(
                update={"certification_status": SecurityCertificationStatus.CONFLICTING}
            )

    def all_records(self) -> tuple[SecurityMasterRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


DEFAULT_SECURITY_MASTER = SecurityMaster()






