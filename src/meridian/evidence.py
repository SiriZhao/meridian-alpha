"""Meridian-owned evidence providers, packet building, and completeness checks.

All providers in this module are offline/replay fixtures.  Vendor SDKs and
network clients deliberately do not appear in the project-owned contracts.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from meridian.config import EvidenceCompletenessPolicy, EvidencePacketPolicy
from meridian.research import ResearchEvidencePacket
from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus, StableModel

_TICKERS = ("AAPL", "MSFT", "NVDA", "META", "GOOGL")


class ProviderCapabilities(StableModel):
    provider_name: str
    supports_live: bool
    supports_historical: bool
    supports_point_in_time: bool
    requires_api_key: bool
    execution_grade: bool
    research_grade: bool


class EvidenceProvider(Protocol):
    capabilities: ProviderCapabilities

    def get_evidence(self, ticker: str, as_of: datetime) -> Sequence[EvidenceItem]: ...


class ResearchMarketEvidenceProvider(EvidenceProvider, Protocol):
    pass


class FundamentalEvidenceProvider(EvidenceProvider, Protocol):
    pass


class NewsEvidenceProvider(EvidenceProvider, Protocol):
    pass


class MacroEvidenceProvider(EvidenceProvider, Protocol):
    pass


class ProviderObservation(StableModel):
    provider: str
    status: str
    item_count: int = 0
    error_code: str | None = None


class EvidenceCompletenessDiagnostics(StableModel):
    complete: bool
    total_items: int
    distinct_sources: int
    missing_evidence_types: tuple[str, ...] = ()
    stale_evidence_types: tuple[str, ...] = ()
    point_in_time_quality: Decimal
    violations: tuple[str, ...] = ()


class EvidenceCompletenessEvaluator:
    def __init__(self, policy: EvidenceCompletenessPolicy):
        self.policy = policy

    def evaluate(
        self, packet: ResearchEvidencePacket, as_of: datetime | None = None
    ) -> EvidenceCompletenessDiagnostics:
        reference = as_of or packet.as_of
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise ValueError("completeness reference time must be timezone-aware")
        items = packet.items
        sources = {item.source for item in items}
        present_types = {item.evidence_type for item in items}
        missing_types = tuple(sorted(set(self.policy.required_evidence_types) - present_types))
        stale_types: set[str] = set()
        for item in items:
            max_age = self.policy.maximum_age_by_type.get(item.evidence_type)
            if max_age is not None and item.available_at is not None:
                if (reference - item.available_at).total_seconds() > max_age:
                    stale_types.add(item.evidence_type)
        quality = self._quality(packet)
        violations: list[str] = []
        if len(items) < self.policy.minimum_total_items:
            violations.append("minimum_total_items")
        if len(sources) < self.policy.minimum_distinct_sources:
            violations.append("minimum_distinct_sources")
        if missing_types:
            violations.append("required_evidence_types")
        if stale_types:
            violations.append("maximum_age_by_type")
        if quality < self.policy.minimum_point_in_time_quality:
            violations.append("minimum_point_in_time_quality")
        return EvidenceCompletenessDiagnostics(
            complete=not violations,
            total_items=len(items),
            distinct_sources=len(sources),
            missing_evidence_types=missing_types,
            stale_evidence_types=tuple(sorted(stale_types)),
            point_in_time_quality=quality,
            violations=tuple(violations),
        )

    @staticmethod
    def _quality(packet: ResearchEvidencePacket) -> Decimal:
        if not packet.items:
            return Decimal("0")
        qualities = {
            "VERIFIED_LIVE_AS_OF": Decimal("1"),
            "CERTIFIED_HISTORICAL_PIT": Decimal("1"),
            "VERIFIED": Decimal("1"),
            "LIVE_RESEARCH_OK": Decimal("1"),
            "RECENT": Decimal("0.75"),
            "HISTORICAL_REPLAY_UNSAFE": Decimal("0"),
            "REPLAY_UNSAFE": Decimal("0"),
            "SYNTHETIC": Decimal("0"),
            "UNVERIFIED": Decimal("0"),
            "UNKNOWN": Decimal("0"),
        }
        return sum(
            (qualities.get(item.point_in_time_status, Decimal("0")) for item in packet.items),
            Decimal("0"),
        ) / Decimal(len(packet.items))


class EvidencePacketBuilder:
    """Gather and normalize bounded evidence without allowing one provider to fail all."""

    def __init__(
        self,
        policy: EvidencePacketPolicy | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy or EvidencePacketPolicy(
            max_total_evidence_items=50,
            max_items_per_type=10,
            max_summary_characters_per_item=2000,
        )
        self.clock = clock or (lambda: datetime.now(UTC))

    def gather(
        self,
        ticker: str,
        as_of: datetime,
        providers: Sequence[EvidenceProvider],
    ) -> ResearchEvidencePacket:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("evidence packet as_of must be timezone-aware")
        normalized: dict[str, EvidenceItem] = {}
        observations: list[ProviderObservation] = []
        warnings: list[str] = []
        synthetic = False
        for provider in providers:
            name = provider.capabilities.provider_name
            try:
                raw_items = provider.get_evidence(ticker.upper(), as_of)
                if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
                    raise TypeError("provider returned a non-sequence evidence result")
                count = 0
                for item in raw_items:
                    if not isinstance(item, EvidenceItem):
                        raise TypeError("provider returned a non-EvidenceItem")
                    enriched = item
                    if enriched.ticker is None:
                        enriched = enriched.model_copy(update={"ticker": ticker.upper()})
                    if enriched.provider is None:
                        enriched = enriched.model_copy(update={"provider": name})
                    if enriched.available_at is None or enriched.available_at > as_of:
                        warnings.append(f"{name}:EVIDENCE_AFTER_AS_OF")
                        continue
                    if self.policy.max_summary_characters_per_item >= 0 and enriched.summary:
                        enriched = enriched.model_copy(
                            update={
                                "summary": enriched.summary[
                                    : self.policy.max_summary_characters_per_item
                                ]
                            }
                        )
                    if enriched.point_in_time_status in {
                        "HISTORICAL_REPLAY_UNSAFE",
                        "SYNTHETIC",
                    } or enriched.source.upper().startswith("SYNTHETIC"):
                        synthetic = True
                    normalized.setdefault(enriched.stable_id, enriched)
                    count += 1
                observations.append(
                    ProviderObservation(provider=name, status="AVAILABLE", item_count=count)
                )
            except Exception as error:  # noqa: BLE001 - isolate provider failures
                observations.append(
                    ProviderObservation(
                        provider=name,
                        status="FAILED",
                        error_code=type(error).__name__,
                    )
                )
                warnings.append(f"{name}:PROVIDER_FAILURE:{type(error).__name__}")

        ordered = sorted(
            normalized.values(),
            key=lambda item: (
                item.available_at or item.observed_at,
                item.evidence_type,
                item.provider or "UNVERIFIED",
                item.source,
                item.stable_id,
            ),
        )
        bounded: list[EvidenceItem] = []
        type_counts: dict[str, int] = {}
        for item in ordered:
            if len(bounded) >= self.policy.max_total_evidence_items:
                break
            count = type_counts.get(item.evidence_type, 0)
            if count >= self.policy.max_items_per_type:
                continue
            bounded.append(item)
            type_counts[item.evidence_type] = count + 1
        if len(bounded) < len(ordered):
            warnings.append("EVIDENCE_BOUNDS_APPLIED")
        if not bounded:
            warnings.append("NO_EVIDENCE_ITEMS")
        ids = ":".join(item.stable_id for item in bounded)
        packet_digest = hashlib.sha256(
            f"{ticker.upper()}|{as_of.isoformat()}|{ids}".encode()
        ).hexdigest()[:24]
        executable_items = {
            "VERIFIED_LIVE_AS_OF",
            "CERTIFIED_HISTORICAL_PIT",
            "VERIFIED",
            "RECENT",
        }
        if synthetic:
            point_status = "HISTORICAL_REPLAY_UNSAFE"
        elif bounded and all(item.point_in_time_status.value in executable_items for item in bounded):
            point_status = "CERTIFIED_HISTORICAL_PIT"
        else:
            point_status = "UNVERIFIED"
        return ResearchEvidencePacket(
            packet_id=f"packet_{packet_digest}",
            ticker=ticker.upper(),
            as_of=as_of,
            created_at=self.clock(),
            items=tuple(bounded),
            provider_statuses=tuple(
                f"{observation.provider}:{observation.status}:{observation.item_count}"
                for observation in observations
            ),
            warnings=tuple(warnings),
            point_in_time_status=EvidencePointInTimeStatus(point_status),
            empty_reason=";".join(warnings) if not bounded else None,
        )


class _SyntheticEvidenceProvider:
    evidence_type = "synthetic"
    provider_prefix = "fake"

    def __init__(self, provider_name: str):
        self.capabilities = ProviderCapabilities(
            provider_name=provider_name,
            supports_live=False,
            supports_historical=True,
            supports_point_in_time=False,
            requires_api_key=False,
            execution_grade=False,
            research_grade=False,
        )

    def get_evidence(self, ticker: str, as_of: datetime) -> tuple[EvidenceItem, ...]:
        if ticker not in _TICKERS:
            return ()
        return (
            EvidenceItem(
                ticker=ticker,
                provider=self.capabilities.provider_name,
                source=f"SYNTHETIC:{self.capabilities.provider_name}",
                observed_at=as_of,
                available_at=as_of,
                evidence_type=self.evidence_type,
                title="SYNTHETIC - NOT LIVE DATA",
                summary="SYNTHETIC - NOT LIVE DATA",
                point_in_time_status=EvidencePointInTimeStatus.HISTORICAL_REPLAY_UNSAFE,
            ),
        )


class FakeMarketEvidenceProvider(_SyntheticEvidenceProvider):
    evidence_type = "market"

    def __init__(self) -> None:
        super().__init__("fake-market-replay")


class FakeFundamentalEvidenceProvider(_SyntheticEvidenceProvider):
    evidence_type = "fundamental"

    def __init__(self) -> None:
        super().__init__("fake-fundamental-replay")


class FakeNewsEvidenceProvider(_SyntheticEvidenceProvider):
    evidence_type = "news"

    def __init__(self) -> None:
        super().__init__("fake-news-replay")


class FakeMacroEvidenceProvider(_SyntheticEvidenceProvider):
    evidence_type = "macro"

    def __init__(self) -> None:
        super().__init__("fake-macro-replay")
