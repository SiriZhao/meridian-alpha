from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.forward_evidence import ForwardLedger, ForwardOutcome, ForwardPrediction
from meridian.intelligence import (
    DipClassification,
    DipScout,
    ResearchAction,
    ResearchPacket,
    StructuredMockIntelligenceProvider,
)

NOW = datetime(2026, 9, 2, 14, 30, tzinfo=UTC)


def packet(*, position: str = "0") -> ResearchPacket:
    return ResearchPacket(symbol="AAPL", analysis_time=NOW, information_cutoff=NOW, price=Decimal("100"), drawdown=Decimal("-0.20"), trend=Decimal("0.1"), volatility=Decimal("0.2"), quant_score=Decimal("0.5"), evidence=({"timestamp": NOW.isoformat(), "provenance": "fixture-event"},), existing_position_weight=Decimal(position), data_quality="FIXTURE")


def response(*, damage: str = "LOW") -> str:
    return json.dumps({"symbol": "AAPL", "thesis": "fixture", "bull_case": "fixture", "bear_case": "fixture", "event_interpretation": "one-off", "fundamental_damage": damage, "temporary_dislocation_probability": "0.8", "conviction": "0.8", "risk_flags": [], "recommended_action_research": "BUY_RESEARCH", "opportunity_score": "0.8", "evidence_refs": ["fixture-event"], "model": "mock", "provider": "test", "prompt_version": "v1", "generated_at": NOW.isoformat(), "information_cutoff": NOW.isoformat()})


def test_malformed_llm_and_risk_block_have_no_order_authority() -> None:
    malformed = StructuredMockIntelligenceProvider("not-json").analyze(packet())
    assert malformed.recommended_action_research is ResearchAction.UNAVAILABLE
    opinion = StructuredMockIntelligenceProvider(response()).analyze(packet(position="0.30"))
    result = DipScout().assess(packet(position="0.30"), opinion, max_add_weight=Decimal("0.10"))
    assert result["classification"] == DipClassification.STRONG_CANDIDATE.value
    assert result["final"] == "WATCH_NO_ORDER"
    assert result["order_authority"] is False


def test_structural_damage_avoids_and_future_evidence_rejected() -> None:
    opinion = StructuredMockIntelligenceProvider(response(damage="STRUCTURAL")).analyze(packet())
    assert DipScout().assess(packet(), opinion, max_add_weight=Decimal("0.10"))["classification"] == DipClassification.AVOID.value
    with pytest.raises(ValueError, match="future evidence"):
        ResearchPacket.model_validate({**packet().model_dump(), "evidence": ({"timestamp": (NOW + timedelta(seconds=1)).isoformat(), "provenance": "future"},)})


def test_forward_evidence_is_append_only_and_maturity_gated(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    prediction = ForwardPrediction(prediction_id="p1", decision_timestamp=NOW, information_cutoff=NOW, symbol="AAPL", price=Decimal("100"), quant_score=Decimal("0.2"), llm_score=Decimal("0.3"), combined_research_score=Decimal("0.25"), model="mock", provider="test", prompt_version="v1", software_version="test", horizon_days=20)
    ledger.append_prediction(prediction)
    with pytest.raises(ValueError, match="NOT_MATURE"):
        ledger.append_outcome(ForwardOutcome(prediction_id="p1", observed_at=NOW + timedelta(days=5), return_20d=Decimal("0.1")))
    ledger.append_outcome(ForwardOutcome(prediction_id="p1", observed_at=NOW + timedelta(days=21), return_20d=Decimal("0.1"), benchmark_return=Decimal("0.02")))
    assert ledger.evaluate()["status"] == "INSUFFICIENT_FORWARD_EVIDENCE"
    with pytest.raises(ValueError, match="IMMUTABLE"):
        ledger.append_prediction(prediction.model_copy(update={"quant_score": Decimal("0.3")}))
