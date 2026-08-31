"""Primary-source Security Master certification for the bounded universe.

Legal identity is deliberately independent from provider symbol lookup.  This
module accepts a caller-supplied, hashed primary-source artifact and returns a
new authoritative record only when the source, identity, and historical
interval are all internally consistent.  It never treats a ticker enum or a
secondary market-data mapping as legal identity evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, model_validator

from meridian.schemas import StableModel
from meridian.security_master import (
    AssetType,
    OfficialIdentityProvenance,
    SecurityCertificationStatus,
    SecurityIdentityHistory,
    SecurityMaster,
    SecurityMasterRecord,
)


class IdentitySourceKind(StrEnum):
    SEC = "SEC"
    ETF_SPONSOR = "ETF_SPONSOR"
    EXCHANGE = "EXCHANGE"
    CBOE = "CBOE"


class ProviderSymbolMapping(StableModel):
    """A provider lookup key; it cannot certify the underlying security."""

    provider: str = Field(min_length=1, max_length=128)
    provider_symbol: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=256)
    source_uri: str | None = Field(default=None, max_length=2000)
    observed_at: datetime
    retrieved_at: datetime | None = None


class IdentityCertificationRequest(StableModel):
    """Evidence needed for one bounded identity promotion attempt."""

    canonical_symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    legal_name: str = Field(min_length=2, max_length=256)
    asset_type: AssetType
    source_kind: IdentitySourceKind
    source_name: str = Field(min_length=1, max_length=256)
    source_uri: str = Field(min_length=1, max_length=2000)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    retrieved_at: datetime
    certified_at: datetime
    effective_from: datetime
    effective_to: datetime | None = None
    exchange: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    cik: str | None = Field(default=None, pattern=r"^\d{10}$")
    provider_mappings: tuple[ProviderSymbolMapping, ...] = ()

    @model_validator(mode="after")
    def validate_request(self) -> IdentityCertificationRequest:
        if self.certified_at < self.retrieved_at:
            raise ValueError("certified_at must not precede retrieved_at")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        if self.effective_from > self.retrieved_at:
            raise ValueError("effective_from cannot be after retrieved_at")
        parsed = urlparse(self.source_uri)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("official identity source must be an HTTPS URI")
        if self.asset_type is AssetType.EQUITY and self.cik is None:
            raise ValueError("SEC identity certification requires CIK")
        return self


class IdentityCertificationResult(StableModel):
    ticker: str
    status: SecurityCertificationStatus
    record: SecurityMasterRecord | None = None
    blockers: tuple[str, ...] = ()


class SecurityMasterPromotionService:
    """Validate and create an authoritative record without implicit mutation."""

    _SEC_HOSTS = frozenset({"sec.gov", "www.sec.gov", "data.sec.gov"})
    _PRIMARY_HOSTS = {
        "SPY": frozenset({"ssga.com", "www.ssga.com"}),
        "GLD": frozenset({"ssga.com", "www.ssga.com"}),
        "QQQ": frozenset({"invesco.com", "www.invesco.com"}),
        "SGOV": frozenset({"ishares.com", "www.ishares.com", "blackrock.com", "www.blackrock.com"}),
        "TLT": frozenset({"ishares.com", "www.ishares.com", "blackrock.com", "www.blackrock.com"}),
        "VIX": frozenset({"cboe.com", "www.cboe.com"}),
    }

    def _source_allowed(self, record: SecurityMasterRecord, request: IdentityCertificationRequest) -> bool:
        host = (urlparse(request.source_uri).hostname or "").lower()
        if record.asset_type is AssetType.EQUITY:
            return request.source_kind is IdentitySourceKind.SEC and host in self._SEC_HOSTS
        if record.canonical_symbol == "VIX":
            return request.source_kind is IdentitySourceKind.CBOE and host in self._PRIMARY_HOSTS["VIX"]
        return request.source_kind in {IdentitySourceKind.ETF_SPONSOR, IdentitySourceKind.EXCHANGE} and host in self._PRIMARY_HOSTS.get(record.canonical_symbol, frozenset())

    def validate(self, record: SecurityMasterRecord, request: IdentityCertificationRequest) -> tuple[str, ...]:
        blockers: list[str] = []
        if record.canonical_symbol != request.canonical_symbol:
            blockers.append("IDENTITY_SYMBOL_MISMATCH")
        if record.asset_type is not request.asset_type:
            blockers.append("IDENTITY_ASSET_TYPE_MISMATCH")
        if record.currency != request.currency:
            blockers.append("IDENTITY_CURRENCY_MISMATCH")
        if record.primary_exchange != request.exchange:
            blockers.append("IDENTITY_EXCHANGE_MISMATCH")
        if record.asset_type is AssetType.EQUITY and request.cik is None:
            blockers.append("IDENTITY_CIK_REQUIRED")
        if record.cik is not None and request.cik != record.cik:
            blockers.append("IDENTITY_CIK_MISMATCH")
        if not self._source_allowed(record, request):
            blockers.append("IDENTITY_PRIMARY_SOURCE_UNVERIFIED")
        if request.source_content_hash is not None and request.source_content_hash != request.source_hash:
            blockers.append("IDENTITY_CONTENT_HASH_MISMATCH")
        return tuple(dict.fromkeys(blockers))

    def promote(self, record: SecurityMasterRecord, request: IdentityCertificationRequest) -> IdentityCertificationResult:
        blockers = self.validate(record, request)
        if blockers:
            return IdentityCertificationResult(
                ticker=record.canonical_symbol,
                status=SecurityCertificationStatus.UNVERIFIED,
                blockers=blockers,
            )
        provenance = OfficialIdentityProvenance(
            source_name=request.source_name,
            source_uri=request.source_uri,
            retrieved_at=request.retrieved_at,
            source_hash=request.source_hash,
            certification_at=request.certified_at,
            identity_type=request.source_kind.value,
            canonical_symbol=request.canonical_symbol,
            legal_name=request.legal_name,
            exchange=request.exchange,
            currency=request.currency,
            effective_from=request.effective_from,
            effective_to=request.effective_to,
        )
        history = SecurityIdentityHistory(
            identifier=record.canonical_symbol,
            identifier_type="CANONICAL_SYMBOL",
            effective_from=request.effective_from,
            effective_to=request.effective_to,
            exchange=request.exchange,
            source=request.source_name,
            source_uri=request.source_uri,
            retrieved_at=request.retrieved_at,
            source_hash=request.source_hash,
        )
        promoted = record.model_copy(
            update={
                "legal_name": request.legal_name,
                "cik": request.cik or record.cik,
                "official_identity_provenance": provenance,
                "identity_history": tuple(item for item in record.identity_history if item.identifier != record.canonical_symbol) + (history,),
                "last_verified_at": request.certified_at,
                "certification_status": SecurityCertificationStatus.AUTHORITATIVE_VERIFIED,
            }
        )
        return IdentityCertificationResult(
            ticker=record.canonical_symbol,
            status=SecurityCertificationStatus.AUTHORITATIVE_VERIFIED,
            record=promoted,
        )

    def promote_into(self, master: SecurityMaster, request: IdentityCertificationRequest) -> IdentityCertificationResult:
        """Explicitly mutate a caller-owned registry after a successful result."""
        record = master.lookup(request.canonical_symbol)
        if record is None:
            return IdentityCertificationResult(
                ticker=request.canonical_symbol,
                status=SecurityCertificationStatus.UNVERIFIED,
                blockers=("SECURITY_IDENTITY_UNAVAILABLE",),
            )
        result = self.promote(record, request)
        if result.record is not None:
            # ``register`` intentionally detects conflicts, so this dedicated
            # explicit method is the only mutation path for certification.
            master._records[record.canonical_symbol] = result.record  # noqa: SLF001
        return result


AuthoritativeIdentityCertificationService = SecurityMasterPromotionService


def authoritative_count(master: SecurityMaster) -> int:
    return sum(
        record.certification_status is SecurityCertificationStatus.AUTHORITATIVE_VERIFIED
        for record in master.all_records()
    )


def source_hash(payload: bytes | str) -> str:
    """Hash the exact primary-source bytes used for a certification request."""
    raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_certified_security_master(path: Path) -> SecurityMaster:
    """Opt-in load of captured authoritative records; default fixtures stay unchanged."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("gate") != "4F":
        raise ValueError("IDENTITY_CAPTURE_REPORT_INVALID")
    records: list[SecurityMasterRecord] = []
    for item in document.get("records", []):
        if not isinstance(item, dict) or item.get("status") != SecurityCertificationStatus.AUTHORITATIVE_VERIFIED.value:
            continue
        identity = item.get("identity")
        if not isinstance(identity, dict):
            continue
        record = SecurityMasterRecord.model_validate(identity)
        if record.certification_status is SecurityCertificationStatus.AUTHORITATIVE_VERIFIED:
            records.append(record)
    if not records:
        raise ValueError("IDENTITY_CAPTURE_REPORT_HAS_NO_CERTIFIED_RECORDS")
    return SecurityMaster(tuple(records))
