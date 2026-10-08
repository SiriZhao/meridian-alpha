"""Deterministic report assembly keeps observed, computed and model claims separate."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, Field

from meridian.daily_research import DailyResearchInput
from meridian.gpt_native_research import NativeResearchResult
from meridian.schemas import StableModel
from meridian.terminal_service import TerminalBrief, research_quality_scorecard


class ObservedResearchPrice(StableModel):
    symbol: str
    price: str
    observed_at: AwareDatetime
    source: str
    evidence_id: str
    freshness: Literal["AS_OF_INPUT_CUTOFF", "STALE_OR_UNKNOWN"]
    certification: Literal["PUBLIC_RESEARCH_UNVERIFIED"] = "PUBLIC_RESEARCH_UNVERIFIED"


class DecisionBrief(StableModel):
    version: Literal["meridian-decision-brief.v1"] = "meridian-decision-brief.v1"
    analysis_cutoff: AwareDatetime
    data_mode: Literal["LIVE", "FIXTURE", "REPLAY", "UNKNOWN"]
    quant_snapshot_hash: str
    observed_facts: tuple[ObservedResearchPrice, ...] = Field(max_length=8)
    deterministic_quant_analysis: dict
    gpt_interpretation: dict | None
    conditional_forecast: dict | None
    risk_constraints: dict
    unknown_information: tuple[str, ...]
    possible_manual_action: None = None
    reason_for_waiting: str
    quality_scorecard: dict | None
    execution_authority: Literal["NONE"] = "NONE"


def generate_decision_brief(terminal: TerminalBrief, *, request: DailyResearchInput | None = None,
                            model_result: NativeResearchResult | None = None) -> DecisionBrief:
    cutoff = terminal.quant.analysis_cutoff
    if request and request.analysis_cutoff != cutoff:
        raise ValueError("DECISION_BRIEF_SHARED_CUTOFF_REQUIRED")
    prices = []
    if request:
        from meridian.config import load_policies
        from meridian.runtime import policy_directory
        max_age = load_policies(policy_directory()).data.quote_max_age_seconds
        for observed in request.observations:
            age = (cutoff - observed.observed_at).total_seconds()
            if age < 0:
                raise ValueError("DECISION_BRIEF_OBSERVATION_AFTER_CUTOFF")
            source = request.provider_provenance.get(observed.ticker)
            if request.freshness_status != "PASS" or age > max_age or not source:
                # No current price claim survives a stale/missing-source gate.
                continue
            prices.append(ObservedResearchPrice(symbol=observed.ticker, price=str(observed.price),
                observed_at=observed.observed_at, source=source, evidence_id=observed.reference,
                freshness="AS_OF_INPUT_CUTOFF"))
    interpretation: dict[str, Any] | None = None
    forecast: dict[str, Any] | None = None
    scorecard = None
    unknowns = ["EXPECTED_RETURN_UNCALIBRATED", "EXECUTION_QUOTES_AND_MANUAL_REVIEW_REQUIRED"]
    if not prices:
        unknowns.append("CURRENT_PRICE_UNAVAILABLE_OR_STALE")
    if model_result:
        catalog = {r.evidence_id for r in terminal.quant.rows}
        model_ids = {e.evidence_id for e in model_result.evidence if e.source == "V2.2_SHADOW_TERMINAL"}
        if model_ids != catalog or any(e.observed_at != cutoff for e in model_result.evidence if e.source == "V2.2_SHADOW_TERMINAL"):
            raise ValueError("DECISION_BRIEF_MODEL_EVIDENCE_IDENTITY_MISMATCH")
        from meridian.terminal_service import terminal_model_context
        view = terminal_model_context(terminal.quant)["quant_terminal_view"]
        expected = {r["signal"]["evidence_id"]: {"signal": r["signal"], "quant": r["quant"],
            "certification": view["certification"], "financial_oos_eligible": False} for r in view["rows"]}
        if any(e.structured_value != expected[e.evidence_id] for e in model_result.evidence if e.source == "V2.2_SHADOW_TERMINAL"):
            raise ValueError("DECISION_BRIEF_MODEL_NUMERICAL_EVIDENCE_MISMATCH")
        interpretation = {"status": model_result.research_state.value,
            "primary": model_result.primary.model_dump(mode="json") if model_result.primary else None,
            "skeptic": model_result.skeptic.model_dump(mode="json") if model_result.skeptic else None,
            "disagreement_score": model_result.disagreement_score,
            "errors": list(model_result.degradation_reasons)}
        if model_result.scenarios:
            forecast = {name: {"description": getattr(model_result.scenarios, name).description,
                "assumptions": list(getattr(model_result.scenarios, name).key_assumptions),
                "invalidators": list(getattr(model_result.scenarios, name).invalidators)} for name in ("bull", "base", "bear")}
            forecast["probabilities"] = None
            forecast["calibration"] = "UNCALIBRATED"
        scorecard = research_quality_scorecard(model_result)
    else:
        unknowns.append("GPT_NOT_RUN")
    return DecisionBrief(analysis_cutoff=cutoff, data_mode=request.mode if request else "UNKNOWN", quant_snapshot_hash=terminal.quant.digest,
        observed_facts=tuple(prices), deterministic_quant_analysis=terminal.views["QUANT_EXPLORER"],
        gpt_interpretation=interpretation, conditional_forecast=forecast,
        risk_constraints=terminal.views["PORTFOLIO_RISK"], unknown_information=tuple(unknowns),
        reason_for_waiting="研究结果未授权交易；缺失的新鲜执行报价、账户或证据必须先补齐，等待是有效选择。",
        quality_scorecard=scorecard)
