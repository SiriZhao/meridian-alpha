"""Machine-readable certification records for connected and candidate providers."""

from __future__ import annotations

from meridian.schemas import StableModel


class ProviderCertificationRecord(StableModel):
    provider_name: str
    domain: str
    network_capable: bool = False
    supports_live: bool = False
    supports_historical: bool = False
    supports_point_in_time: bool = False
    supports_vintage: bool = False
    supports_bid: bool = False
    supports_ask: bool = False
    supports_last: bool = False
    research_grade: bool = False
    execution_quote_grade: bool = False
    timestamp_semantics: str
    provenance_semantics: str
    authentication: str
    rate_limit: str
    current_certification: str
    failure_behavior: str


_PROVIDER_RECORDS = (
    ProviderCertificationRecord(
        provider_name="yahoo",
        domain="market_quote_and_ohlcv",
        network_capable=True,
        supports_live=True,
        supports_historical=True,
        supports_last=True,
        timestamp_semantics="regularMarketTime/chart epoch normalized to UTC; delay and publication timing unverified",
        provenance_semantics="provider symbol plus retrieved timestamp and source URI",
        authentication="none observed",
        rate_limit="UNVERIFIED",
        current_certification="SHADOW_UNVERIFIED",
        failure_behavior="timeout/malformed/identity errors fail closed per ticker",
    ),
    ProviderCertificationRecord(
        provider_name="sec-edgar",
        domain="fundamentals",
        network_capable=True,
        supports_live=True,
        supports_historical=True,
        timestamp_semantics="filed date is available only at date precision; acceptance/publication PIT unverified",
        provenance_semantics="CIK, accession/document identity and SEC URI",
        authentication="none",
        rate_limit="SEC fair-access policy requires supervised review",
        current_certification="CODE_ONLY_UNVERIFIED",
        failure_behavior="provider failure isolated; no fabricated fundamental item",
    ),
    ProviderCertificationRecord(
        provider_name="replay-fundamental/news/macro",
        domain="offline_evidence",
        supports_historical=True,
        timestamp_semantics="fixture cutoff only",
        provenance_semantics="synthetic source identifiers",
        authentication="none",
        rate_limit="none",
        current_certification="SYNTHETIC_NON_EXECUTABLE",
        failure_behavior="fixture absence is explicit",
    ),
    ProviderCertificationRecord(
        provider_name="sec-edgar-accession-certified",
        domain="fundamentals_and_filing_events",
        network_capable=True,
        supports_historical=True,
        supports_point_in_time=True,
        research_grade=True,
        timestamp_semantics="SEC submissions acceptanceDateTime normalized to UTC; exact accession join required",
        provenance_semantics="CIK, accession, primary document, SEC submissions URI, retrieval time, content hash",
        authentication="none",
        rate_limit="SEC fair-access policy; bounded requests only",
        current_certification="PIT_CAPABLE_PER_OBSERVATION",
        failure_behavior="missing/mismatched/late acceptance metadata emits no certified item",
    ),    ProviderCertificationRecord(
        provider_name="stooq-public",
        domain="market_quote",
        network_capable=True,
        supports_last=True,
        timestamp_semantics="CSV date/time semantics unverified; current endpoint returned HTTP 404",
        provenance_semantics="public CSV URI",
        authentication="none",
        rate_limit="UNVERIFIED",
        current_certification="DIAGNOSTIC_ONLY",
        failure_behavior="HTTP/malformed response fails closed",
    ),
    ProviderCertificationRecord(
        provider_name="polygon-read-only-candidate",
        domain="execution_quote_candidate",
        network_capable=True,
        supports_live=True,
        supports_bid=True,
        supports_ask=True,
        supports_last=True,
        timestamp_semantics="Documented endpoint fields require supervised plan/feed verification",
        provenance_semantics="Candidate only; symbol, exchange event, and retrieval lineage must be certified per observation",
        authentication="API key required; no key configured",
        rate_limit="Plan-dependent; not verified",
        current_certification="TO_BE_SELECTED",
        failure_behavior="No configured adapter; candidate cannot authorize a manual ticket",
    ),
)


def provider_certification_registry() -> tuple[ProviderCertificationRecord, ...]:
    """Return deterministic certification metadata for audit/reporting."""
    return _PROVIDER_RECORDS


def provider_certification_map() -> dict[str, ProviderCertificationRecord]:
    return {record.provider_name: record for record in _PROVIDER_RECORDS}
