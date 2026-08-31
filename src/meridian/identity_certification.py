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
from datetime import UTC, datetime
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


SECURITY_MASTER_BOUNDED_UNIVERSE = (
    "AAPL", "MSFT", "NVDA", "META", "GOOGL", "SPY", "QQQ", "SGOV", "GLD", "TLT", "VIX",
)


class SecurityCertificationManifest(StableModel):
    """Integrity envelope for a captured primary-source certificate set."""

    schema_version: str = "1"
    generated_at: datetime
    capture_set_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bounded_universe_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    bounded_universe: tuple[str, ...] = Field(min_length=1)
    record_digests: dict[str, str] = Field(min_length=1)
    source_content_hashes: dict[str, str] = Field(default_factory=dict)
    certification_policy_version: str = Field(min_length=1, max_length=64)
    manifest_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    def digest_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"manifest_digest"})

    @classmethod
    def build(cls, document: dict[str, object], *, generated_at: datetime | None = None, policy_version: str = "gate6a.v1") -> SecurityCertificationManifest:
        records = document.get("records")
        if not isinstance(records, list):
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:records")
        by_symbol: dict[str, dict[str, object]] = {}
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("CERTIFICATE_ARTIFACT_INVALID:record")
            identity = item.get("identity")
            ticker = item.get("ticker")
            if not isinstance(identity, dict) or not isinstance(ticker, str):
                raise ValueError("CERTIFICATE_ARTIFACT_INVALID:identity")
            by_symbol[ticker.upper()] = identity
        universe = tuple(symbol for symbol in SECURITY_MASTER_BOUNDED_UNIVERSE if symbol in by_symbol)
        digests = {
            symbol: hashlib.sha256(json.dumps(by_symbol[symbol], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for symbol in sorted(by_symbol)
        }
        capture_set_hash = hashlib.sha256("|".join(f"{symbol}:{digests[symbol]}" for symbol in sorted(digests)).encode()).hexdigest()
        bounded_hash = hashlib.sha256("|".join(universe).encode()).hexdigest()
        source_hashes: dict[str, str] = {}
        for symbol in universe:
            provenance = by_symbol[symbol].get("official_identity_provenance")
            if isinstance(provenance, dict):
                source_hashes[symbol] = str(provenance.get("source_hash", ""))
        timestamp = generated_at or datetime.now(UTC)
        draft = cls(
            generated_at=timestamp,
            capture_set_hash=capture_set_hash,
            bounded_universe_hash=bounded_hash,
            bounded_universe=universe,
            record_digests=digests,
            source_content_hashes=source_hashes,
            certification_policy_version=policy_version,
            manifest_digest="0" * 64,
        )
        digest = hashlib.sha256(json.dumps(draft.digest_payload(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return draft.model_copy(update={"manifest_digest": digest})

    def verify(self) -> None:
        expected = hashlib.sha256(json.dumps(self.digest_payload(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if expected != self.manifest_digest:
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:manifest_digest")


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
    """Strict compatibility alias for the manifest-verifying loader."""
    return load_verified_security_certificates(path)


def write_security_certification_manifest(
    path: Path, manifest_path: Path | None = None, *, policy_version: str = "gate6a.v1"
) -> SecurityCertificationManifest:
    """Create the sidecar manifest for a captured Gate 4F report."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError
        manifest = SecurityCertificationManifest.build(document, policy_version=policy_version)
        target = manifest_path or path.with_name(f"{path.stem}.manifest.json")
        target.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("CERTIFICATE_ARTIFACT_INVALID"):
            raise
        raise ValueError("CERTIFICATE_ARTIFACT_INVALID:manifest_build") from error


def load_verified_security_certificates(
    path: Path, manifest_path: Path | None = None
) -> SecurityMaster:
    """Load a captured certificate set only after all digests and identities verify."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("gate") != "4F":
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:document")
        target = manifest_path or path.with_name(f"{path.stem}.manifest.json")
        if target.exists():
            manifest_raw = json.loads(target.read_text(encoding="utf-8"))
        else:
            manifest_raw = document.get("manifest")
        if not isinstance(manifest_raw, dict):
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:manifest_missing")
        manifest = SecurityCertificationManifest.model_validate(manifest_raw)
        manifest.verify()
        if tuple(manifest.bounded_universe) != SECURITY_MASTER_BOUNDED_UNIVERSE:
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:bounded_universe")
        records_raw = document.get("records")
        if not isinstance(records_raw, list):
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:records")
        by_symbol: dict[str, dict[str, object]] = {}
        for item in records_raw:
            if not isinstance(item, dict):
                raise ValueError("CERTIFICATE_ARTIFACT_INVALID:record")
            ticker = item.get("ticker")
            identity = item.get("identity")
            if not isinstance(ticker, str) or not isinstance(identity, dict):
                raise ValueError("CERTIFICATE_ARTIFACT_INVALID:identity")
            symbol = ticker.upper()
            if symbol in by_symbol:
                raise ValueError("CERTIFICATE_ARTIFACT_INVALID:duplicate_symbol")
            by_symbol[symbol] = identity
            expected_digest = manifest.record_digests.get(symbol)
            actual_digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if expected_digest != actual_digest:
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:record_digest:{symbol}")
            if item.get("status") != SecurityCertificationStatus.AUTHORITATIVE_VERIFIED.value:
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:status:{symbol}")
            provenance = identity.get("official_identity_provenance")
            if not isinstance(provenance, dict):
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:provenance:{symbol}")
            if item.get("source_hash") != provenance.get("source_hash"):
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:source_hash:{symbol}")
            if item.get("source_uri") != provenance.get("source_uri"):
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:source_uri:{symbol}")
            if manifest.source_content_hashes.get(symbol) != provenance.get("source_hash"):
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:source_content_hash:{symbol}")
            history = identity.get("identity_history")
            if not isinstance(history, list) or not history:
                raise ValueError(f"CERTIFICATE_ARTIFACT_INVALID:historical_interval:{symbol}")
        if set(by_symbol) != set(SECURITY_MASTER_BOUNDED_UNIVERSE):
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:universe_records")
        recomputed_capture = hashlib.sha256("|".join(f"{symbol}:{manifest.record_digests[symbol]}" for symbol in sorted(manifest.record_digests)).encode()).hexdigest()
        if recomputed_capture != manifest.capture_set_hash:
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:capture_set_hash")
        records = tuple(SecurityMasterRecord.model_validate(by_symbol[symbol]) for symbol in SECURITY_MASTER_BOUNDED_UNIVERSE)
        if any(record.certification_status is not SecurityCertificationStatus.AUTHORITATIVE_VERIFIED for record in records):
            raise ValueError("CERTIFICATE_ARTIFACT_INVALID:non_authoritative_record")
        return SecurityMaster(records)
    except ValueError:
        raise
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("CERTIFICATE_ARTIFACT_INVALID:read") from error


# Explicit name used by production/shadow callers; the legacy loader remains
# available for backwards-compatible Gate 4 tests but is not a certification
# promotion path.
load_verified_security_master = load_verified_security_certificates
