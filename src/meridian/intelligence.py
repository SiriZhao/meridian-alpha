"""Structured advisory intelligence; no object here can authorize an order."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from meridian.schemas import StableModel


class IntelligenceMode(StrEnum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"
    ADVISORY = "ADVISORY"
    VALIDATED_OVERLAY = "VALIDATED_OVERLAY"


class ResearchAction(StrEnum):
    BUY_RESEARCH = "BUY_RESEARCH"
    WATCH = "WATCH"
    AVOID = "AVOID"
    UNAVAILABLE = "RESEARCH_UNAVAILABLE"


class ResearchPacket(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    analysis_time: datetime
    information_cutoff: datetime
    price: Decimal = Field(gt=0)
    drawdown: Decimal | None = Field(default=None, ge=-1, le=0)
    trend: Decimal | None = Field(default=None, ge=-1, le=1)
    volatility: Decimal | None = Field(default=None, ge=0)
    quant_score: Decimal = Field(ge=-1, le=1)
    evidence: tuple[dict[str, str], ...] = ()
    existing_position_weight: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    data_quality: str = "UNKNOWN"

    @model_validator(mode="after")
    def no_future_evidence(self) -> ResearchPacket:
        if self.information_cutoff > self.analysis_time:
            raise ValueError("information_cutoff is after analysis_time")
        for item in self.evidence:
            timestamp = item.get("timestamp")
            provenance = item.get("provenance")
            if not timestamp or not provenance:
                raise ValueError("research evidence requires timestamp and provenance")
            if datetime.fromisoformat(timestamp.replace("Z", "+00:00")) > self.information_cutoff:
                raise ValueError("future evidence is not allowed")
        return self


class ResearchOpinion(StableModel):
    symbol: str
    thesis: str
    bull_case: str
    bear_case: str
    event_interpretation: str
    fundamental_damage: str
    temporary_dislocation_probability: Decimal = Field(ge=0, le=1)
    conviction: Decimal = Field(ge=0, le=1)
    risk_flags: tuple[str, ...] = ()
    recommended_action_research: ResearchAction
    opportunity_score: Decimal = Field(ge=0, le=1)
    evidence_refs: tuple[str, ...] = ()
    model: str
    provider: str
    prompt_version: str
    generated_at: datetime
    information_cutoff: datetime

    @model_validator(mode="after")
    def validate_cutoff(self) -> ResearchOpinion:
        if self.generated_at < self.information_cutoff:
            raise ValueError("generated_at is before information cutoff")
        return self


class IntelligenceProvider(Protocol):
    def analyze(self, packet: ResearchPacket) -> ResearchOpinion: ...


class DisabledIntelligenceProvider:
    def analyze(self, packet: ResearchPacket) -> ResearchOpinion:
        return ResearchOpinion(symbol=packet.symbol, thesis="Research provider unavailable.", bull_case="UNKNOWN", bear_case="UNKNOWN", event_interpretation="UNKNOWN", fundamental_damage="UNKNOWN", temporary_dislocation_probability=Decimal("0"), conviction=Decimal("0"), risk_flags=("RESEARCH_UNAVAILABLE",), recommended_action_research=ResearchAction.UNAVAILABLE, opportunity_score=Decimal("0"), evidence_refs=(), model="UNAVAILABLE", provider="DISABLED", prompt_version="v1", generated_at=packet.analysis_time, information_cutoff=packet.information_cutoff)


class StructuredMockIntelligenceProvider:
    """Deterministic test provider; external providers must validate this schema."""
    def __init__(self, response_json: str) -> None:
        self.response_json = response_json

    def analyze(self, packet: ResearchPacket) -> ResearchOpinion:
        try:
            raw = json.loads(self.response_json)
            opinion = ResearchOpinion.model_validate(raw)
        except (ValueError, TypeError) as error:
            return DisabledIntelligenceProvider().analyze(packet).model_copy(update={"risk_flags": ("RESEARCH_UNAVAILABLE", type(error).__name__)})
        if opinion.symbol != packet.symbol or opinion.information_cutoff != packet.information_cutoff:
            return DisabledIntelligenceProvider().analyze(packet).model_copy(update={"risk_flags": ("RESEARCH_UNAVAILABLE", "CUTOFF_OR_SYMBOL_MISMATCH")})
        return opinion


class DipClassification(StrEnum):
    STRONG_CANDIDATE = "STRONG_CANDIDATE"
    CANDIDATE = "CANDIDATE"
    WATCH = "WATCH"
    AVOID = "AVOID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DipScout:
    def assess(self, packet: ResearchPacket, opinion: ResearchOpinion, *, max_add_weight: Decimal) -> dict[str, object]:
        if packet.drawdown is None or packet.volatility is None:
            classification = DipClassification.INSUFFICIENT_DATA
        elif opinion.recommended_action_research is ResearchAction.AVOID or opinion.fundamental_damage.upper() in {"HIGH", "STRUCTURAL"}:
            classification = DipClassification.AVOID
        elif packet.drawdown <= Decimal("-0.15") and packet.quant_score > 0 and opinion.temporary_dislocation_probability >= Decimal("0.70"):
            classification = DipClassification.STRONG_CANDIDATE
        elif packet.drawdown <= Decimal("-0.10") and opinion.conviction >= Decimal("0.50"):
            classification = DipClassification.CANDIDATE
        else:
            classification = DipClassification.WATCH
        risk_block = packet.existing_position_weight >= max_add_weight
        return {"symbol": packet.symbol, "classification": classification.value, "confidence": str(opinion.conviction), "quant_score": str(packet.quant_score), "research_action": opinion.recommended_action_research.value, "risk_status": "BLOCK_ADD" if risk_block else "PASS", "final": "WATCH_NO_ORDER" if risk_block else classification.value, "order_authority": False}
