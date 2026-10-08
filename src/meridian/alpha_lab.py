"""Deterministic, isolated challenger research. No executable outputs.

Scores are experimental signals, not realized returns. The lab deliberately
declines financial ranking without a reviewed, aligned walk-forward dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.alpha_fusion import research_modifier
from meridian.authorization import CertifiedAgentSignal
from meridian.schemas import StableModel
from meridian.trading_calendar import NEW_YORK, is_trading_session, session_close


def require_lab_path(path: Path) -> None:
    resolved = path.resolve()
    normalized = str(resolved).replace("\\", "/").casefold()
    if "meridianalpharuntime" in normalized or "alpha-lab" not in {part.casefold() for part in resolved.parts}:
        raise ValueError("ALPHA_LAB_ISOLATED_DIRECTORY_REQUIRED")
    if path.suffix.casefold() != ".json":
        raise ValueError("ALPHA_LAB_JSON_ARCHIVE_REQUIRED")


def operational_score(daily_return: Decimal) -> Decimal:
    """Exact current operational score; no retrospective normalization."""
    if not daily_return.is_finite():
        raise ValueError("ALPHA_LAB_NONFINITE_RETURN")
    return max(Decimal("0"), daily_return)


class LabBar(StableModel):
    timestamp: AwareDatetime
    available_at: AwareDatetime
    close: Decimal = Field(gt=0, allow_inf_nan=False)
    source: str = Field(min_length=1)
    adjustment_basis: Literal["CONSISTENT_REVIEWED", "UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def availability(self) -> LabBar:
        session = self.timestamp.astimezone(NEW_YORK).date()
        if session.year not in {2026, 2027, 2028} or not is_trading_session(session) or self.timestamp != session_close(session):
            raise ValueError("ALPHA_LAB_DEFINED_SESSION_CLOSE_REQUIRED")
        if self.available_at < self.timestamp:
            raise ValueError("ALPHA_LAB_BAR_AVAILABLE_BEFORE_OBSERVATION")
        return self


class LabInput(StableModel):
    symbol: str = Field(min_length=1)
    as_of: AwareDatetime
    daily_return: Decimal = Field(allow_inf_nan=False)
    daily_return_available_at: AwareDatetime
    bars: tuple[LabBar, ...] = ()
    evidence_origin: Literal["SYNTHETIC_FIXTURE", "PUBLIC_UNVERIFIED", "REVIEWED_RESEARCH"]

    @model_validator(mode="after")
    def cutoff(self) -> LabInput:
        if self.daily_return_available_at > self.as_of:
            raise ValueError("ALPHA_LAB_DAILY_RETURN_AFTER_CUTOFF")
        if any(bar.timestamp > self.as_of or bar.available_at > self.as_of for bar in self.bars):
            raise ValueError("ALPHA_LAB_HISTORY_AFTER_CUTOFF")
        timestamps = [bar.timestamp for bar in self.bars]
        if timestamps != sorted(set(timestamps)):
            raise ValueError("ALPHA_LAB_HISTORY_UNORDERED_OR_DUPLICATE")
        return self


class ChallengerScore(StableModel):
    challenger: str
    symbol: str
    score: Decimal | None
    status: Literal["AVAILABLE", "INSUFFICIENT_EVIDENCE"]
    factors: dict[str, Decimal] = Field(default_factory=dict)
    research_contribution: Decimal = Decimal("0")
    certificate_id: str | None = None
    reason: str | None = None


def challenger_scores(data: LabInput, certified: CertifiedAgentSignal | None = None) -> tuple[ChallengerScore, ...]:
    """Fixed ex-ante recipe. No fitting, routing or calls to a model.

Multi-factor V1: 21 close observations, .4 20-interval momentum, .3 trend
    relative to their arithmetic mean, .2 drawdown, -.1 realized volatility.
    Decimal precision is scoped so callers cannot change results globally.
"""
    cash = ChallengerScore(challenger="CASH", symbol=data.symbol, score=Decimal("0"), status="AVAILABLE")
    baseline = ChallengerScore(challenger="OPERATIONAL_QUANT", symbol=data.symbol, score=operational_score(data.daily_return), status="AVAILABLE")
    from meridian.forward_evidence import advance_sessions
    selected_bars = data.bars[-21:]
    contiguous = all(advance_sessions(a.timestamp.astimezone(NEW_YORK).date(), 1) == b.timestamp.astimezone(NEW_YORK).date() for a, b in zip(selected_bars[:-1], selected_bars[1:], strict=True))
    if len(data.bars) < 21 or not contiguous or any(bar.adjustment_basis != "CONSISTENT_REVIEWED" for bar in selected_bars):
        multifactor = ChallengerScore(challenger="MULTIFACTOR_V1", symbol=data.symbol, score=None,
                                      status="INSUFFICIENT_EVIDENCE", reason="21_REVIEWED_CONSISTENT_CLOSES_REQUIRED")
    else:
        with localcontext() as context:
            context.prec = 28
            closes = [bar.close for bar in data.bars[-21:]]
            returns = [b / a - 1 for a, b in zip(closes[:-1], closes[1:], strict=True)]
            mean = sum(returns, Decimal("0")) / len(returns)
            volatility = (sum(((item - mean) ** 2 for item in returns), Decimal("0")) / len(returns)).sqrt()
            factors = {"momentum_20": closes[-1] / closes[0] - 1,
                       "trend_21": closes[-1] / (sum(closes, Decimal("0")) / len(closes)) - 1,
                       "drawdown_21": closes[-1] / max(closes) - 1, "volatility_20": volatility}
            score = max(Decimal("-1"), min(Decimal("1"), Decimal(".4") * factors["momentum_20"] + Decimal(".3") * factors["trend_21"] + Decimal(".2") * factors["drawdown_21"] - Decimal(".1") * volatility))
        multifactor = ChallengerScore(challenger="MULTIFACTOR_V1", symbol=data.symbol, score=score, status="AVAILABLE", factors=factors)
    contribution = Decimal("0")
    certificate_id = None
    reason = "NO_CERTIFIED_RESEARCH_ZERO_CONTRIBUTION"
    if certified is not None:
        if not isinstance(certified, CertifiedAgentSignal):
            raise TypeError("ALPHA_LAB_CERTIFIED_RESEARCH_REQUIRED")
        if certified.ticker != data.symbol or certified.as_of != data.as_of:
            raise ValueError("ALPHA_LAB_RESEARCH_IDENTITY_OR_CUTOFF_MISMATCH")
        contribution = research_modifier(certified)
        certificate_id = certified.certificate_id
        reason = None
    enhanced = ChallengerScore(challenger="QUANT_PLUS_CERTIFIED_LLM", symbol=data.symbol,
                               score=max(Decimal("-1"), min(Decimal("1"), baseline.score + contribution)) if baseline.score is not None else None,
                               status="AVAILABLE", research_contribution=contribution, certificate_id=certificate_id, reason=reason)
    return cash, baseline, multifactor, enhanced


class TemporalLabel(StableModel):
    decision_at: AwareDatetime
    mature_at: AwareDatetime
    available_at: AwareDatetime

    @model_validator(mode="after")
    def order(self) -> TemporalLabel:
        if not self.decision_at < self.mature_at <= self.available_at:
            raise ValueError("ALPHA_LAB_LABEL_TIME_INVALID")
        return self


def purged_training_indices(labels: tuple[TemporalLabel, ...], *, test_start: AwareDatetime) -> tuple[int, ...]:
    """Strictly historical labels; endpoint equality is purged too."""
    if test_start.tzinfo is None or test_start.utcoffset() is None:
        raise ValueError("ALPHA_LAB_TEST_START_TIMEZONE_REQUIRED")
    return tuple(index for index, label in enumerate(labels) if label.decision_at < test_start and label.available_at < test_start)


def lab_report(data: LabInput, certified: CertifiedAgentSignal | None = None) -> dict[str, object]:
    scores = challenger_scores(data, certified)
    digest = hashlib.sha256(data.stable_json().encode()).hexdigest()
    research_digest = hashlib.sha256(certified.stable_json().encode()).hexdigest() if certified else None
    recipe = {"version": "ALPHA_LAB_V1", "lookback_sessions": 21,
              "factor_weights": {"momentum": ".4", "trend": ".3", "drawdown": ".2", "volatility": "-.1"},
              "research_modifier": "EXISTING_CERTIFIED_BASE_MODIFIER_V1", "promotion": "DISABLED"}
    experiment_digest = hashlib.sha256(json.dumps({"input": digest, "research": research_digest, "recipe": recipe}, sort_keys=True).encode()).hexdigest()
    return {"schema_version": "meridian-alpha-lab.v1", "title": "Quant vs Quant+LLM Shadow Evaluation",
            "input_digest": digest, "as_of": data.as_of.isoformat(), "symbol": data.symbol,
            "research_digest": research_digest, "recipe": recipe, "experiment_digest": experiment_digest,
            "evidence_origin": data.evidence_origin, "challengers": [score.model_dump(mode="json") for score in scores],
            "evaluation_status": "NOT_EVALUABLE", "conclusion": "INCONCLUSIVE", "financial_sample_count": 0,
            "reason": "NO_ALIGNED_REVIEWED_OUT_OF_SAMPLE_PORTFOLIO_RETURNS",
            "model_invocations": 0, "model_cost": "UNKNOWN", "execution_authority": "NONE",
            "account": "Schwab-Paper", "account_environment": "PAPER", "broker_submission": "DISABLED",
            "automatic_strategy_promotion": "DISABLED", "production_policy_changed": False}


def render_lab_report(report: dict[str, object]) -> str:
    return "# Quant vs Quant+LLM Shadow Evaluation\n\n" + str(report["evaluation_status"]) + " / " + str(report["conclusion"]) + "\n\nNo financial ranking: " + str(report["reason"]) + "\n\n```json\n" + json.dumps(report, indent=2, sort_keys=True) + "\n```\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only isolated alpha research laboratory")
    parser.add_argument("command", choices=("score", "reconcile"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--closes", type=Path)
    parser.add_argument("--as-of", type=datetime.fromisoformat)
    args = parser.parse_args()
    try:
        if args.command == "score":
            report = lab_report(LabInput.model_validate_json(args.input.read_text(encoding="utf-8")))
        else:
            from meridian.dated_close import load_reviewed_pairs, reconcile_closes
            from meridian.forward_evidence import ForwardLedger
            if args.as_of is None:
                raise ValueError("ALPHA_LAB_RECONCILIATION_AS_OF_REQUIRED")
            if not args.input.is_file() or (args.closes is not None and not args.closes.is_file()):
                raise ValueError("ALPHA_LAB_EVIDENCE_FILE_NOT_FOUND")
            ledger = ForwardLedger(args.input)
            predictions = tuple(ledger.predictions.values())
            report = reconcile_closes(predictions, load_reviewed_pairs(args.closes) if args.closes else (), as_of=args.as_of, outcomes=tuple(ledger.outcomes.values()))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__, "message": "Invalid laboratory evidence; inspect input locally. No state was written."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
