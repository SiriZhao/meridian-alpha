from datetime import UTC, datetime
from decimal import Decimal

import pytest

from meridian.authorization import EvidenceAuthorizationService
from meridian.evidence import EvidencePacketBuilder, ProviderCapabilities
from meridian.research import GroundedResearchSignal, GroundedResearchStatus, ResearchEvidencePacket
from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus

AS_OF = datetime(2026, 8, 28, 14, 30, tzinfo=UTC)


def _item(provider: str, status: EvidencePointInTimeStatus, *, source: str | None = None) -> EvidenceItem:
    return EvidenceItem(
        ticker="AAPL",
        provider=provider,
        source=source or f"{provider}-source",
        observed_at=AS_OF,
        available_at=AS_OF,
        evidence_type="market",
        point_in_time_status=status,
    )


def _caps(provider: str, *, historical: bool = True, live: bool = False) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_name=provider,
        supports_live=live,
        supports_historical=historical,
        supports_point_in_time=True,
        requires_api_key=False,
        execution_grade=False,
        research_grade=True,
    )


def _packet(items: tuple[EvidenceItem, ...], status: EvidencePointInTimeStatus) -> ResearchEvidencePacket:
    return ResearchEvidencePacket(
        packet_id="packet-cert",
        ticker="AAPL",
        as_of=AS_OF,
        created_at=AS_OF,
        items=items,
        point_in_time_status=status,
    )


def _grounded(items: tuple[EvidenceItem, ...]) -> GroundedResearchSignal:
    return GroundedResearchSignal(
        ticker="AAPL",
        as_of=AS_OF,
        direction="BULLISH",
        conviction=Decimal("0.7"),
        thesis="multi-source certified fixture",
        cited_evidence_ids=tuple(item.stable_id for item in items),
        status=GroundedResearchStatus.AVAILABLE,
    )


def test_packet_mixed_verified_and_certified_does_not_upgrade_to_historical_pit() -> None:
    items = (
        _item("a", EvidencePointInTimeStatus.VERIFIED),
        _item("b", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
    )
    packet = EvidencePacketBuilder.aggregate_point_in_time_status(items)
    assert packet is EvidencePointInTimeStatus.UNVERIFIED


def test_packet_requires_homogeneous_explicit_historical_certification() -> None:
    items = (
        _item("a", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
        _item("b", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
    )
    assert EvidencePacketBuilder.aggregate_point_in_time_status(items) is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT


@pytest.mark.parametrize(
    "statuses",
    [
        (EvidencePointInTimeStatus.RECENT, EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
        (EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF, EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
        (EvidencePointInTimeStatus.UNVERIFIED, EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
        (EvidencePointInTimeStatus.SYNTHETIC, EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
    ],
)
def test_packet_mixed_statuses_fail_closed(statuses: tuple[EvidencePointInTimeStatus, EvidencePointInTimeStatus]) -> None:
    items = tuple(_item(provider, status) for provider, status in zip(("a", "b"), statuses, strict=True))
    assert EvidencePacketBuilder.aggregate_point_in_time_status(items) is not EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT


def test_multi_provider_registry_authorizes_each_citation_with_its_own_certificate() -> None:
    items = (_item("market-a", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT), _item("news-b", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT))
    packet = _packet(items, EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    certificate = EvidenceAuthorizationService().authorize(
        _grounded(items),
        packet,
        provider_registry={"market-a": _caps("market-a"), "news-b": _caps("news-b")},
    )
    assert certificate.evidence_ids == tuple(item.stable_id for item in items)
    assert certificate.provider_name == "market-a,news-b"


def test_missing_provider_certificate_fails_closed() -> None:
    items = (_item("market-a", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT), _item("news-b", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT))
    with pytest.raises(ValueError, match="PROVIDER_CAPABILITY_UNAVAILABLE"):
        EvidenceAuthorizationService().authorize(
            _grounded(items),
            _packet(items, EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
            provider_registry={"market-a": _caps("market-a")},
        )


def test_single_provider_certificate_cannot_authorize_another_provider() -> None:
    item = _item("news-b", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    with pytest.raises(ValueError, match="PROVIDER_CAPABILITY_UNAVAILABLE|provider"):
        EvidenceAuthorizationService().authorize(
            _grounded((item,)),
            _packet((item,), EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
            provider_capabilities=_caps("market-a"),
        )


def test_provider_capability_pit_claim_mismatch_fails_closed() -> None:
    item = _item("live-only", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    with pytest.raises(ValueError, match="historical"):
        EvidenceAuthorizationService().authorize(
            _grounded((item,)),
            _packet((item,), EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
            provider_capabilities=_caps("live-only", historical=False, live=True),
        )


def test_provider_registry_unknown_name_is_not_silently_defaulted() -> None:
    item = _item("unknown", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    with pytest.raises(ValueError, match="PROVIDER_CAPABILITY_UNAVAILABLE"):
        EvidenceAuthorizationService().authorize(
            _grounded((item,)),
            _packet((item,), EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),
            provider_registry={},
        )


def test_provider_certification_registry_is_conservative() -> None:
    from meridian.provider_registry import provider_certification_map

    registry = provider_certification_map()
    assert registry["yahoo"].network_capable is True
    assert registry["yahoo"].execution_quote_grade is False
    assert registry["sec-edgar"].supports_point_in_time is False
    assert registry["replay-fundamental/news/macro"].network_capable is False


def test_packet_claim_cannot_overstate_item_pit_certification() -> None:
    item = _item("market-a", EvidencePointInTimeStatus.VERIFIED)
    packet = _packet((item,), EvidencePointInTimeStatus.VERIFIED_LIVE_AS_OF)
    with pytest.raises(ValueError, match="overstates"):
        EvidenceAuthorizationService().authorize(
            _grounded((item,)), packet, provider_registry={"market-a": _caps("market-a", live=True)}
        )

def test_certified_view_filters_mixed_context_before_normalization() -> None:
    from meridian.research import CertifiedEvidenceView, ResearchContextPacket

    safe = _item("sec-accepted", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    yahoo = _item("yahoo", EvidencePointInTimeStatus.UNVERIFIED)
    synthetic = _item("replay", EvidencePointInTimeStatus.SYNTHETIC)
    future = _item("future", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT).model_copy(
        update={"available_at": AS_OF.replace(year=AS_OF.year + 1)}
    )
    context = ResearchContextPacket(
        context_id="mixed-context", ticker="AAPL", as_of=AS_OF, created_at=AS_OF,
        items=(safe, yahoo, synthetic, future),
    )
    view = CertifiedEvidenceView.from_context(
        context,
        provider_registry={
            "sec-accepted": _caps("sec-accepted"),
            "yahoo": _caps("yahoo"),
            "replay": _caps("replay"),
            "future": _caps("future"),
        },
        clock=lambda: AS_OF,
    )
    assert tuple(item.provider for item in view.packet.items) == ("sec-accepted",)
    assert sum("PIT_NOT_EXECUTABLE" in exclusion for exclusion in view.excluded) == 2
    assert any("AFTER_DECISION_AS_OF" in exclusion for exclusion in view.excluded)


def test_certified_view_is_sealed() -> None:
    from meridian.research import CertifiedEvidenceView

    with pytest.raises(ValueError, match="only be built"):
        CertifiedEvidenceView(packet=_packet((_item("safe", EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT),), EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT), context_id="bypass")