"""Reviewed research closes, never execution quotes or broker authority.

Public downloads remain unverified. Verification here means a documented human
review of a research return basis, not certification of an execution feed.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.forward_evidence import ForwardLedger, ForwardOutcome, ForwardPrediction
from meridian.runtime_io import atomic_write, run_lock
from meridian.schemas import StableModel
from meridian.trading_calendar import is_trading_session, session_close


class CloseStatus(StrEnum):
    VERIFIED = "VERIFIED_HORIZON_CLOSE"
    PUBLIC = "PUBLIC_UNVERIFIED_CLOSE"
    ADJUSTMENT_UNKNOWN = "ADJUSTMENT_UNKNOWN"
    CONFLICT = "SOURCE_CONFLICT"
    NOT_MATURE = "NOT_MATURE"
    MISSING = "MISSING_EVIDENCE"
    UNSUPPORTED_ACTION = "UNRESOLVED_CORPORATE_ACTION"


class CorporateAction(StableModel):
    kind: Literal["SPLIT", "REVERSE_SPLIT", "CASH_DIVIDEND", "SPECIAL_DIVIDEND", "SYMBOL_CHANGE", "SUSPENSION", "DELISTING"]
    effective_at: AwareDatetime
    available_at: AwareDatetime
    source: str = Field(min_length=1)
    ratio: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    cash_per_share: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def terms(self) -> CorporateAction:
        if self.kind in {"SPLIT", "REVERSE_SPLIT"}:
            if self.ratio is None or self.cash_per_share is not None:
                raise ValueError("CLOSE_SPLIT_TERMS_REQUIRED")
        elif self.kind in {"CASH_DIVIDEND", "SPECIAL_DIVIDEND"}:
            if self.cash_per_share is None or self.ratio is not None:
                raise ValueError("CLOSE_DIVIDEND_TERMS_REQUIRED")
        elif self.ratio is not None or self.cash_per_share is not None:
            raise ValueError("CLOSE_UNSUPPORTED_ACTION_TERMS")
        return self


class DatedClose(StableModel):
    symbol: str = Field(min_length=1)
    session_date: date
    close_basis: Literal["DEFINED_UNADJUSTED_SESSION_CLOSE"]
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: Literal["USD"] = "USD"
    source: str = Field(min_length=1)
    source_timestamp: AwareDatetime
    available_at: AwareDatetime
    ingested_at: AwareDatetime
    origin: Literal["PUBLIC_DOWNLOAD", "HUMAN_REVIEWED_LOCAL", "SYNTHETIC_FIXTURE"]
    adjustment_status: Literal["UNADJUSTED", "UNKNOWN"]

    @model_validator(mode="after")
    def timestamps(self) -> DatedClose:
        if self.session_date.year not in {2026, 2027, 2028}:
            raise ValueError("CLOSE_REVIEWED_CALENDAR_SCOPE_2026_2028_REQUIRED")
        if not is_trading_session(self.session_date) or self.source_timestamp != session_close(self.session_date):
            raise ValueError("CLOSE_SESSION_TIMESTAMP_MISMATCH")
        if not self.source_timestamp <= self.available_at <= self.ingested_at:
            raise ValueError("CLOSE_TIMESTAMP_ORDER_INVALID")
        return self

    @property
    def evidence_digest(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class ReviewedPricePair(StableModel):
    """A receipt binds *all* prices/actions to one immutable prediction.

The reviewer attests complete action coverage from decision to horizon. This is
an explicit trust boundary; the application does not authenticate a reviewer.
Cash dividends are retained as cash, never described as reinvested total return.
"""

    prediction: ForwardPrediction
    terminal: DatedClose
    benchmark_terminal: DatedClose
    corporate_action_basis: Literal["UNADJUSTED_SHARE_AND_CASH_HOLDING_PERIOD"]
    inception_basis: Literal["UNADJUSTED_DECISION_PRICE"]
    inception_evidence_origin: Literal["PUBLIC_UNVERIFIED", "REVIEWED_LOCAL", "SYNTHETIC_FIXTURE"] = "PUBLIC_UNVERIFIED"
    actions: tuple[CorporateAction, ...] = ()
    benchmark_actions: tuple[CorporateAction, ...] = ()
    action_coverage_complete: bool = False
    reviewed_digest: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    reviewer_reference: str | None = None
    reviewed_at: AwareDatetime | None = None

    @property
    def evidence_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"reviewed_digest", "reviewer_reference", "reviewed_at"})
        return hashlib.sha256(self.__class__.model_validate(payload).stable_json().encode()).hexdigest()


class CloseEvaluation(StableModel):
    prediction_id: str
    evidence_digest: str
    validation_status: CloseStatus
    reasons: tuple[str, ...] = ()
    return_at_horizon: Decimal | None = None
    benchmark_return: Decimal | None = None
    financial_sample_eligible: bool = False
    quote_certification: Literal["BLOCKED"] = "BLOCKED"
    automatic_promotion: Literal["DISABLED"] = "DISABLED"


class ReviewedCloseArchive(StableModel):
    schema_version: Literal["meridian-dated-close.v1"]
    pairs: tuple[ReviewedPricePair, ...]


def holding_period_return(initial: Decimal, terminal: Decimal, actions: tuple[CorporateAction, ...]) -> Decimal:
    """One inception share; distributions use then-current share count.

Same-instant events are ambiguous and rejected rather than arbitrarily ordered.
"""
    if initial <= 0 or terminal <= 0:
        raise ValueError("CLOSE_PRICE_INVALID")
    if len({action.effective_at for action in actions}) != len(actions):
        raise ValueError("CLOSE_ACTION_ORDER_AMBIGUOUS")
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        shares, cash = Decimal("1"), Decimal("0")
        for action in sorted(actions, key=lambda item: item.effective_at):
            if action.kind in {"SPLIT", "REVERSE_SPLIT"} and action.ratio is not None:
                shares *= action.ratio
            elif action.kind in {"CASH_DIVIDEND", "SPECIAL_DIVIDEND"} and action.cash_per_share is not None:
                cash += shares * action.cash_per_share
            else:
                raise ValueError("CLOSE_ACTION_UNRESOLVED")
        return (shares * terminal + cash) / initial - Decimal("1")


def evaluate_close(pair: ReviewedPricePair, *, as_of: AwareDatetime) -> CloseEvaluation:
    prediction = pair.prediction
    def blocked(status: CloseStatus, reason: str) -> CloseEvaluation:
        return CloseEvaluation(prediction_id=prediction.prediction_id, evidence_digest=pair.evidence_digest, validation_status=status, reasons=(reason,))

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("CLOSE_AS_OF_TIMEZONE_REQUIRED")
    if as_of < prediction.maturity_at:
        return blocked(CloseStatus.NOT_MATURE, "HORIZON_NOT_COMPLETE")
    if prediction.maturity_session is None or prediction.trading_session is None or prediction.benchmark_price is None:
        return blocked(CloseStatus.MISSING, "INCEPTION_OR_SESSION_PROVENANCE_MISSING")
    for close, symbol in ((pair.terminal, prediction.symbol), (pair.benchmark_terminal, prediction.benchmark)):
        if close.symbol != symbol or close.session_date != prediction.maturity_session:
            return blocked(CloseStatus.CONFLICT, "EXACT_SYMBOL_AND_MATURITY_REQUIRED")
        if close.ingested_at > as_of:
            return blocked(CloseStatus.MISSING, "EVIDENCE_NOT_AVAILABLE_AT_EVALUATION")
        if close.adjustment_status != "UNADJUSTED":
            return blocked(CloseStatus.ADJUSTMENT_UNKNOWN, "PRICE_BASIS_UNKNOWN")
    if not pair.action_coverage_complete:
        return blocked(CloseStatus.ADJUSTMENT_UNKNOWN, "ACTION_COVERAGE_NOT_ATTESTED")
    actions = (*pair.actions, *pair.benchmark_actions)
    if any(not prediction.decision_timestamp < action.effective_at <= prediction.maturity_at or action.available_at > as_of for action in actions):
        return blocked(CloseStatus.CONFLICT, "ACTION_INTERVAL_OR_AVAILABILITY_INVALID")
    if any(action.kind in {"SYMBOL_CHANGE", "SUSPENSION", "DELISTING"} for action in actions):
        return blocked(CloseStatus.UNSUPPORTED_ACTION, "TERMINAL_IDENTITY_OR_DISTRIBUTION_UNRESOLVED")
    if any(close.origin != "HUMAN_REVIEWED_LOCAL" for close in (pair.terminal, pair.benchmark_terminal)):
        return blocked(CloseStatus.PUBLIC, "PUBLIC_OR_FIXTURE_EVIDENCE_IS_NOT_FINANCIAL_VERIFICATION")
    if pair.inception_evidence_origin != "REVIEWED_LOCAL":
        return blocked(CloseStatus.PUBLIC, "INCEPTION_PRICES_NOT_REVIEWED")
    if pair.reviewed_digest != pair.evidence_digest or not pair.reviewer_reference or pair.reviewed_at is None:
        return blocked(CloseStatus.PUBLIC, "REVIEW_RECEIPT_REQUIRED")
    if not max(pair.terminal.ingested_at, pair.benchmark_terminal.ingested_at) <= pair.reviewed_at <= as_of:
        return blocked(CloseStatus.CONFLICT, "REVIEW_TIMESTAMP_INVALID")
    try:
        asset_return = holding_period_return(prediction.price, pair.terminal.price, pair.actions)
        benchmark_return = holding_period_return(prediction.benchmark_price, pair.benchmark_terminal.price, pair.benchmark_actions)
    except ValueError as error:
        return blocked(CloseStatus.UNSUPPORTED_ACTION, str(error))
    except DecimalException:
        return blocked(CloseStatus.ADJUSTMENT_UNKNOWN, "RETURN_ARITHMETIC_UNREPRESENTABLE")
    return CloseEvaluation(prediction_id=prediction.prediction_id, evidence_digest=pair.evidence_digest, validation_status=CloseStatus.VERIFIED, return_at_horizon=asset_return,
                           benchmark_return=benchmark_return, financial_sample_eligible=True)


def append_reviewed_pair(path: Path, pair: ReviewedPricePair) -> str:
    """A separate lab archive; never mutate the canonical forward/paper ledger."""
    from meridian.alpha_lab import require_lab_path
    require_lab_path(path)
    if pair.reviewed_at is None or not evaluate_close(pair, as_of=pair.reviewed_at).financial_sample_eligible:
        raise ValueError("CLOSE_REVIEWED_RECEIPT_REQUIRED_FOR_IMMUTABLE_ARCHIVE")
    with run_lock(path.parent / ".close-locks", pair.prediction.prediction_id, name="dated-close"):
        existing = load_reviewed_pairs(path)
        previous = next((item for item in existing if item.prediction.prediction_id == pair.prediction.prediction_id), None)
        if previous is not None:
            if previous.stable_json() != pair.stable_json():
                raise ValueError("CLOSE_OUTCOME_IMMUTABLE")
            return "EXISTS"
        import json
        archive = ReviewedCloseArchive(schema_version="meridian-dated-close.v1", pairs=(*existing, pair))
        content = json.dumps(archive.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        atomic_write(path, content)
    return "APPENDED"


def ingest_reviewed_outcome(ledger: ForwardLedger, pair: ReviewedPricePair, *, as_of: AwareDatetime) -> CloseEvaluation:
    """Commit only into an explicitly isolated ledger, using existing locking.

Outcome ingestion is resumable and immutable. The embedded receipt is rechecked
against the frozen prediction whenever the forward ledger is reopened.
"""
    from meridian.alpha_lab import require_lab_path
    require_lab_path(ledger.path)
    prediction = ledger.predictions.get(pair.prediction.prediction_id)
    if prediction is None or prediction.content_hash != pair.prediction.content_hash:
        raise ValueError("CLOSE_FROZEN_PREDICTION_REQUIRED")
    evaluation = evaluate_close(pair, as_of=as_of)
    if not evaluation.financial_sample_eligible:
        return evaluation
    outcome = ForwardOutcome(prediction_id=prediction.prediction_id,
        observed_at=pair.reviewed_at or as_of, return_at_horizon=evaluation.return_at_horizon,
        benchmark_return=evaluation.benchmark_return, benchmark_symbol=prediction.benchmark,
        terminal_price=pair.terminal.price, price_timestamp=prediction.maturity_at,
        price_quality="VERIFIED_HORIZON_CLOSE", outcome_source="HUMAN_REVIEWED_RESEARCH_CLOSE",
        close_evidence=pair.model_dump(mode="json"))
    ledger.append_outcome(outcome)
    return evaluation


def load_reviewed_pairs(path: Path) -> tuple[ReviewedPricePair, ...]:
    if not path.exists():
        return ()
    archive = ReviewedCloseArchive.model_validate_json(path.read_text(encoding="utf-8"))
    pairs = archive.pairs
    if len({pair.prediction.prediction_id for pair in pairs}) != len(pairs):
        raise ValueError("CLOSE_ARCHIVE_DUPLICATE_PREDICTION")
    if any(pair.reviewed_at is None or not evaluate_close(pair, as_of=pair.reviewed_at).financial_sample_eligible for pair in pairs):
        raise ValueError("CLOSE_ARCHIVE_REVIEW_PROVENANCE_INVALID")
    return pairs


def reconcile_closes(predictions: tuple[ForwardPrediction, ...], pairs: tuple[ReviewedPricePair, ...], *, as_of: AwareDatetime, minimum_samples: int = 20, outcomes: tuple[ForwardOutcome, ...] = ()) -> dict[str, object]:
    """Read-only counts; row count is not independent portfolio evidence."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("CLOSE_AS_OF_TIMEZONE_REQUIRED")
    if minimum_samples < 1 or len({p.prediction_id for p in predictions}) != len(predictions) or len({p.canonical_authority_key for p in predictions}) != len(predictions):
        raise ValueError("CLOSE_RECONCILIATION_INPUT_INVALID")
    index = {pair.prediction.prediction_id: pair for pair in pairs}
    if len(index) != len(pairs):
        raise ValueError("CLOSE_ARCHIVE_DUPLICATE_PREDICTION")
    known = {prediction.prediction_id for prediction in predictions}
    if set(index) - known:
        raise ValueError("CLOSE_ARCHIVE_ORPHAN_PREDICTION")
    outcome_index = {outcome.prediction_id: outcome for outcome in outcomes if outcome.observed_at <= as_of}
    if len({outcome.prediction_id for outcome in outcomes}) != len(outcomes) or any(outcome.prediction_id not in known for outcome in outcomes):
        raise ValueError("CLOSE_OUTCOME_IDENTITY_INVALID")
    for outcome in outcome_index.values():
        if outcome.close_evidence is not None:
            embedded = ReviewedPricePair.model_validate(outcome.close_evidence)
            previous = index.get(outcome.prediction_id)
            if previous is not None and previous.stable_json() != embedded.stable_json():
                raise ValueError("CLOSE_RECEIPT_SOURCE_CONFLICT")
            index[outcome.prediction_id] = embedded
    rows: list[CloseEvaluation] = []
    missing = pending = 0
    for prediction in predictions:
        pair = index.get(prediction.prediction_id)
        if pair is not None and pair.prediction.content_hash != prediction.content_hash:
            raise ValueError("CLOSE_PREDICTION_IDENTITY_CONFLICT")
        if as_of < prediction.maturity_at:
            pending += 1
        elif pair is None and prediction.prediction_id not in outcome_index:
            missing += 1
        if pair is not None:
            rows.append(evaluate_close(pair, as_of=as_of))
        elif prediction.prediction_id in outcome_index:
            outcome = outcome_index[prediction.prediction_id]
            outcome.validate_prediction(prediction)
            rows.append(CloseEvaluation(prediction_id=prediction.prediction_id, evidence_digest=outcome.content_hash,
                        validation_status=CloseStatus.PUBLIC, reasons=("LEGACY_OUTCOME_WITHOUT_REVIEWED_CLOSE_RECEIPT",)))
    verified = sum(row.financial_sample_eligible for row in rows)
    return {"schema_version": "meridian-close-reconciliation.v1", "as_of": as_of.isoformat(),
            "PREDICTIONS": len(predictions), "MATURED": sum(p.maturity_at <= as_of for p in predictions),
            "VERIFIED": verified, "UNVERIFIED": sum(row.validation_status is CloseStatus.PUBLIC for row in rows),
            "PENDING": pending, "MISSING": missing + sum(row.validation_status is CloseStatus.MISSING for row in rows),
            "MISSING_REVIEWED_CLOSE": sum(prediction.maturity_at <= as_of and prediction.prediction_id not in index for prediction in predictions),
            "CONFLICTED": sum(row.validation_status is CloseStatus.CONFLICT for row in rows),
            "UNRESOLVED": sum(row.validation_status in {CloseStatus.ADJUSTMENT_UNKNOWN, CloseStatus.UNSUPPORTED_ACTION, CloseStatus.MISSING} for row in rows),
            "EVALUATION_ELIGIBLE": verified >= minimum_samples,
            "sample_definition": "REVIEWED_SYMBOL_HORIZON_ROWS_NOT_INDEPENDENT_PORTFOLIO_SAMPLES",
            "status": "EVALUATION_ELIGIBLE" if verified >= minimum_samples else "INSUFFICIENT_EVIDENCE",
            "automatic_promotion": "DISABLED", "quote_certification": "BLOCKED",
            "rows": [row.model_dump(mode="json") for row in rows]}
