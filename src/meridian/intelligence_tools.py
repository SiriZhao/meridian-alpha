"""Thin, read/calculation-only surface for future MCP/Skill registration."""

from __future__ import annotations

from decimal import Decimal

from meridian.intelligence import DipScout, DisabledIntelligenceProvider, ResearchPacket


def health() -> dict[str, object]:
    return {"intelligence_mode": "ADVISORY", "external_provider": "UNAVAILABLE_UNLESS_EXPLICITLY_CONFIGURED", "execution_authority": False}


def dip_scout(packet: ResearchPacket, *, max_add_weight: Decimal = Decimal("0.10")) -> dict[str, object]:
    """Return an advisory scout result; it cannot create an order."""
    opinion = DisabledIntelligenceProvider().analyze(packet)
    return {"packet": packet.model_dump(mode="json"), "opinion": opinion.model_dump(mode="json"), "assessment": DipScout().assess(packet, opinion, max_add_weight=max_add_weight), "execution_authority": False}
