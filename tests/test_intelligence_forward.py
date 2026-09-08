from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from meridian.config import ForwardEvidencePolicy, ForwardHorizonPolicy
from meridian.forward_evidence import (
    ForwardLedger,
    ForwardOutcome,
    ForwardPrediction,
    advance_sessions,
    freeze_canonical_predictions,
)
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



def forward_policy() -> ForwardEvidencePolicy:
    return ForwardEvidencePolicy(
        benchmark="SPY",
        minimum_mature_samples=20,
        horizons=(ForwardHorizonPolicy(name="SHORT", trading_sessions=1),),
        allowed_modes=("PURE_QUANT", "QUANT_PLUS_LLM"),
    )


def test_forward_freeze_is_authoritative_idempotent_and_session_aware(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    cutoff = datetime(2026, 11, 25, 16, 30, tzinfo=UTC)
    assert advance_sessions(date(2026, 11, 25), 1) == date(2026, 11, 27)  # Thanksgiving
    payload: dict[str, Any] = dict(
        policy=forward_policy(),
        decision_run_id="daily-forward",
        decision_timestamp=cutoff,
        information_cutoff=cutoff,
        account_reference="paper-account",
        universe=("AAPL", "SPY"),
        prices={"AAPL": Decimal("100"), "SPY": Decimal("500")},
        quant_scores={"AAPL": Decimal("0.2"), "SPY": Decimal("0")},
        target_weights={"AAPL": Decimal("0.1")},
        order_signals={"AAPL": "BUY"},
        cash_weight=Decimal("0.9"),
        market_snapshot_hash="market-hash",
        policy_digest="policy-hash",
        model_config_digest="model-hash",
        research_available=False,
        data_mode="OPERATIONAL_PUBLIC",
    )
    first = freeze_canonical_predictions(ledger, **payload)
    assert first["status"] == "FORWARD_FROZEN"
    assert len(ledger.predictions) == 2
    second = freeze_canonical_predictions(ledger, **payload)
    assert second["frozen"] == []
    assert len(ledger.predictions) == 2
    with pytest.raises(ValueError, match="AUTHORITATIVE_PREDICTION_CONFLICT"):
        freeze_canonical_predictions(ledger, **{**payload, "prices": {"AAPL": Decimal("101"), "SPY": Decimal("500")}})
    prediction = next(item for item in ledger.predictions.values() if item.symbol == "AAPL")
    assert prediction.maturity_session == date(2026, 11, 27)
    assert prediction.source_status == "OPERATIONAL_PUBLIC_NOT_CERTIFIED"
    assert prediction.target_weight == Decimal("0.1")


def test_forward_ingestion_waits_for_maturity_and_is_idempotent(tmp_path: Path) -> None:
    ledger = ForwardLedger(tmp_path / "forward.json")
    cutoff = datetime(2026, 3, 6, 16, 30, tzinfo=UTC)
    freeze_canonical_predictions(
        ledger, policy=forward_policy(), decision_run_id="daily-forward", decision_timestamp=cutoff,
        information_cutoff=cutoff, account_reference="paper-account", universe=("AAPL", "SPY"),
        prices={"AAPL": Decimal("100"), "SPY": Decimal("500")}, quant_scores={}, target_weights={},
        order_signals={}, cash_weight=Decimal("1"), market_snapshot_hash="market", policy_digest="policy",
        model_config_digest="model", research_available=False, data_mode="OPERATIONAL_PUBLIC",
    )
    prediction = next(item for item in ledger.predictions.values() if item.symbol == "AAPL")
    early = ledger.ingest_prices(observed_at=prediction.maturity_at - timedelta(seconds=1), prices={"AAPL": Decimal("110"), "SPY": Decimal("510")})
    assert early["status"] == "FORWARD_OUTCOME_NOT_READY"
    mature = ledger.ingest_prices(observed_at=prediction.maturity_at, prices={"AAPL": Decimal("110"), "SPY": Decimal("510")})
    assert len(ledger.outcomes) == 2
    repeat = ledger.ingest_prices(observed_at=prediction.maturity_at, prices={"AAPL": Decimal("110"), "SPY": Decimal("510")})
    assert repeat["appended"] == []
    status = ledger.evaluate()
    assert status["maturity_status"] == "NOT_MATURE"
    assert status["promotion_readiness"] == "NOT_ELIGIBLE_AUTOMATIC_PROMOTION_DISABLED"
