"""Append-only, cutoff-bound forward evidence for canonical daily decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import AwareDatetime, Field, model_validator

from meridian.config import ForwardEvidencePolicy
from meridian.runtime_io import atomic_write, run_lock
from meridian.schemas import StableModel
from meridian.trading_calendar import (
    NEW_YORK,
    is_trading_session,
    latest_completed_session,
    session_close,
)


class ForwardMode(StrEnum):
    PURE_QUANT = "PURE_QUANT"
    QUANT_PLUS_PROBABILITY = "QUANT_PLUS_PROBABILITY"
    QUANT_PLUS_LLM = "QUANT_PLUS_LLM"
    QUANT_PLUS_PROBABILITY_PLUS_LLM = "QUANT_PLUS_PROBABILITY_PLUS_LLM"
    FULL_INTELLIGENCE_ADAPTIVE_EXPOSURE = "FULL_INTELLIGENCE_ADAPTIVE_EXPOSURE"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def advance_sessions(start: date, count: int) -> date:
    """Return the session ``count`` sessions after ``start`` (NYSE calendar)."""
    if count < 1:
        raise ValueError("FORWARD_HORIZON_SESSION_COUNT_INVALID")
    candidate = start
    seen = 0
    while seen < count:
        candidate += timedelta(days=1)
        if is_trading_session(candidate):
            seen += 1
    return candidate


class ForwardPrediction(StableModel):
    """An immutable per-symbol prediction frozen from one canonical decision."""

    prediction_id: str
    decision_timestamp: AwareDatetime
    information_cutoff: AwareDatetime
    symbol: str
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    quant_score: Decimal
    llm_score: Decimal | None = None
    combined_research_score: Decimal
    model: str
    provider: str
    prompt_version: str
    software_version: str
    horizon_days: int = Field(ge=1, le=2520)
    # v2 provenance. Defaults retain readable v1 evidence without promoting it.
    authority_key: str | None = None
    decision_run_id: str | None = None
    trading_session: date | None = None
    maturity_session: date | None = None
    horizon_name: str = "LEGACY_CALENDAR_DAYS"
    universe: tuple[str, ...] = ()
    benchmark: str = "SPY"
    benchmark_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    mode: ForwardMode = ForwardMode.PURE_QUANT
    policy_hash: str | None = None
    model_config_hash: str | None = None
    market_snapshot_hash: str | None = None
    signal: str = "HOLD"
    target_weight: Decimal | None = None
    exposure: Decimal | None = None
    source_status: str = "LEGACY_UNVERIFIED"

    @model_validator(mode="after")
    def no_future_cutoff(self) -> ForwardPrediction:
        if self.information_cutoff > self.decision_timestamp:
            raise ValueError("FORWARD_INFORMATION_CUTOFF_AFTER_DECISION")
        if self.trading_session is not None and self.maturity_session is not None:
            if not is_trading_session(self.trading_session) or self.maturity_session != advance_sessions(self.trading_session, self.horizon_days):
                raise ValueError("FORWARD_MATURITY_SESSION_INVALID")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()

    @property
    def canonical_authority_key(self) -> str:
        if self.authority_key:
            return self.authority_key
        return "legacy-" + self.prediction_id

    @property
    def maturity_at(self) -> datetime:
        if self.maturity_session is not None:
            return session_close(self.maturity_session)
        return self.information_cutoff + timedelta(days=self.horizon_days)


class ForwardOutcome(StableModel):
    prediction_id: str
    observed_at: AwareDatetime
    return_5d: Decimal | None = None
    return_20d: Decimal | None = None
    return_60d: Decimal | None = None
    benchmark_return: Decimal | None = None
    max_adverse_excursion: Decimal | None = None
    max_favorable_excursion: Decimal | None = None
    terminal_price: Decimal | None = None
    return_at_horizon: Decimal | None = None
    benchmark_symbol: str | None = None
    outcome_source: str = "LEGACY_UNVERIFIED"
    price_timestamp: AwareDatetime | None = None
    price_quality: str = Field(default="UNVERIFIED", pattern="^(UNVERIFIED|VERIFIED_HORIZON_CLOSE)$")
    close_evidence: dict[str, object] | None = None

    @model_validator(mode="after")
    def verified_requires_price_provenance(self) -> ForwardOutcome:
        if self.price_quality == "VERIFIED_HORIZON_CLOSE" and (self.price_timestamp is None or self.price_timestamp > self.observed_at or self.terminal_price is None or self.benchmark_return is None):
            raise ValueError("FORWARD_VERIFIED_OUTCOME_PROVENANCE_REQUIRED")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()

    def validate_prediction(self, prediction: ForwardPrediction) -> None:
        if self.observed_at < prediction.maturity_at:
            raise ValueError("FORWARD_OUTCOME_NOT_MATURE")
        if self.price_quality == "VERIFIED_HORIZON_CLOSE":
            terminal = self.terminal_price
            if self.price_timestamp != prediction.maturity_at or self.benchmark_return is None or terminal is None:
                raise ValueError("FORWARD_VERIFIED_OUTCOME_PROVENANCE_REQUIRED")
            if self.benchmark_symbol != prediction.benchmark:
                raise ValueError("FORWARD_BENCHMARK_MISMATCH")
            if self.close_evidence is not None:
                from meridian.dated_close import ReviewedPricePair, evaluate_close
                pair = ReviewedPricePair.model_validate(self.close_evidence)
                result = evaluate_close(pair, as_of=self.observed_at)
                if pair.prediction.content_hash != prediction.content_hash or not result.financial_sample_eligible or self.return_at_horizon != result.return_at_horizon or self.benchmark_return != result.benchmark_return or terminal != pair.terminal.price:
                    raise ValueError("FORWARD_REVIEWED_CLOSE_PROVENANCE_MISMATCH")
            elif not terminal.is_finite() or terminal <= 0 or self.return_at_horizon != terminal / prediction.price - Decimal("1"):
                raise ValueError("FORWARD_OUTCOME_RETURN_MISMATCH")


class ForwardPriceObservation(StableModel):
    """An explicitly dated session close, including corporate-action coverage."""
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    source_timestamp: AwareDatetime
    received_at: AwareDatetime
    source: str
    corporate_action_status: str = Field(default="UNKNOWN", pattern="^(UNKNOWN|NONE_VERIFIED|ADJUSTED_VERIFIED)$")
    price_kind: str = Field(default="SESSION_CLOSE", pattern="^SESSION_CLOSE$")

    @model_validator(mode="after")
    def ordered(self) -> ForwardPriceObservation:
        if self.source_timestamp > self.received_at:
            raise ValueError("FORWARD_PRICE_FUTURE")
        return self


class ForwardLedger:
    """Small durable ledger; evidence is immutable and never a promotion authority."""

    schema_version = "forward-evidence.v2"

    def __init__(self, path: Path) -> None:
        self.path = path
        self.predictions: dict[str, ForwardPrediction] = {}
        self.outcomes: dict[str, ForwardOutcome] = {}
        if path.is_file():
            self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("FORWARD_EVIDENCE_CORRUPT") from error
        if not isinstance(raw, dict):
            raise ValueError("FORWARD_EVIDENCE_CORRUPT")
        if raw.get("schema_version") not in {"forward-evidence.v1", self.schema_version}:
            raise ValueError("FORWARD_EVIDENCE_SCHEMA_UNSUPPORTED")
        if not isinstance(raw.get("predictions", []), list) or not isinstance(raw.get("outcomes", []), list):
            raise ValueError("FORWARD_EVIDENCE_CORRUPT")
        self.predictions, self.outcomes = {}, {}
        authorities: set[str] = set()
        for item in raw.get("predictions", []):
            prediction = ForwardPrediction.model_validate(item)
            previous = self.predictions.get(prediction.prediction_id)
            if previous is not None and previous.content_hash != prediction.content_hash:
                raise ValueError("FORWARD_EVIDENCE_CORRUPT")
            if previous is None and prediction.canonical_authority_key in authorities:
                raise ValueError("FORWARD_EVIDENCE_DUPLICATE_AUTHORITY")
            authorities.add(prediction.canonical_authority_key)
            self.predictions[prediction.prediction_id] = prediction
        for item in raw.get("outcomes", []):
            outcome = ForwardOutcome.model_validate(item)
            if outcome.prediction_id not in self.predictions:
                raise ValueError("FORWARD_EVIDENCE_CORRUPT")
            previous_outcome = self.outcomes.get(outcome.prediction_id)
            if previous_outcome is not None and previous_outcome.content_hash != outcome.content_hash:
                raise ValueError("FORWARD_EVIDENCE_DUPLICATE_OUTCOME")
            outcome.validate_prediction(self.predictions[outcome.prediction_id])
            self.outcomes[outcome.prediction_id] = outcome

    def append_prediction(self, prediction: ForwardPrediction) -> str:
        return self._transaction(prediction)

    def _transaction(self, item: ForwardPrediction | ForwardOutcome) -> str:
        with run_lock(self.path.parent / ".forward-locks", item.prediction_id, name=_hash(str(self.path.resolve()))[:24]):
            if self.path.is_file():
                self._load()
            previous_predictions, previous_outcomes = dict(self.predictions), dict(self.outcomes)
            try:
                return self._append_prediction(item) if isinstance(item, ForwardPrediction) else self._append_outcome(item)
            except Exception:
                self.predictions, self.outcomes = previous_predictions, previous_outcomes
                raise

    def _append_prediction(self, prediction: ForwardPrediction) -> str:
        previous = self.predictions.get(prediction.prediction_id)
        if previous is not None:
            if previous.content_hash != prediction.content_hash:
                if prediction.authority_key is not None:
                    raise ValueError("FORWARD_AUTHORITATIVE_PREDICTION_CONFLICT")
                raise ValueError("FORWARD_PREDICTION_IMMUTABLE")
            return "EXISTS"
        for existing in self.predictions.values():
            if existing.canonical_authority_key == prediction.canonical_authority_key:
                if existing.content_hash != prediction.content_hash:
                    raise ValueError("FORWARD_AUTHORITATIVE_PREDICTION_CONFLICT")
                return "EXISTS"
        self.predictions[prediction.prediction_id] = prediction
        self._write()
        return "APPENDED"

    def append_outcome(self, outcome: ForwardOutcome) -> str:
        return self._transaction(outcome)

    def _append_outcome(self, outcome: ForwardOutcome) -> str:
        prediction = self.predictions.get(outcome.prediction_id)
        if prediction is None:
            raise ValueError("FORWARD_PREDICTION_UNKNOWN")
        outcome.validate_prediction(prediction)
        previous = self.outcomes.get(outcome.prediction_id)
        if previous is not None:
            if previous.content_hash != outcome.content_hash:
                raise ValueError("FORWARD_OUTCOME_IMMUTABLE")
            return "EXISTS"
        self.outcomes[outcome.prediction_id] = outcome
        self._write()
        return "APPENDED"

    def ingest_prices(
        self,
        *,
        observed_at: datetime,
        prices: Mapping[str, Decimal],
        benchmark_prices: Mapping[str, Decimal] | None = None,
        source: str = "OPERATIONAL_MARKET_SNAPSHOT",
        observations: Mapping[str, ForwardPriceObservation] | None = None,
    ) -> dict[str, object]:
        """Join only mature records using the caller's already-validated snapshot."""
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("FORWARD_OUTCOME_TIMEZONE_REQUIRED")
        benchmark_prices = benchmark_prices or prices
        appended: list[str] = []
        pending: list[str] = []
        missing: list[str] = []
        unaligned: list[str] = []
        for prediction in tuple(self.predictions.values()):
            if prediction.prediction_id in self.outcomes:
                continue
            if observed_at < prediction.maturity_at:
                pending.append(prediction.prediction_id)
                continue
            terminal = prices.get(prediction.symbol)
            benchmark_terminal = benchmark_prices.get(prediction.benchmark)
            quality = "UNVERIFIED"
            if observations is not None:
                price_observation = observations.get(prediction.symbol)
                benchmark_observation = observations.get(prediction.benchmark)
                if price_observation is None or benchmark_observation is None:
                    missing.append(prediction.prediction_id)
                    continue
                if any(item.source_timestamp != prediction.maturity_at or item.received_at > observed_at or item.corporate_action_status != "NONE_VERIFIED" for item in (price_observation, benchmark_observation)):
                    unaligned.append(prediction.prediction_id)
                    continue
                terminal, benchmark_terminal = price_observation.price, benchmark_observation.price
                quality = "VERIFIED_HORIZON_CLOSE"
            elif observed_at != prediction.maturity_at:
                # A later intraday quote cannot substitute for the horizon close.
                unaligned.append(prediction.prediction_id)
                continue
            if terminal is None or not terminal.is_finite() or terminal <= 0 or benchmark_terminal is None or not benchmark_terminal.is_finite() or benchmark_terminal <= 0:
                missing.append(prediction.prediction_id)
                continue
            # The benchmark inception price must be part of the prediction, so
            # no later information determines either side of an excess return.
            benchmark_start = prediction.benchmark_price
            if benchmark_start is None or benchmark_start <= 0:
                missing.append(prediction.prediction_id)
                continue
            value = (terminal / prediction.price) - Decimal("1")
            benchmark_return = (benchmark_terminal / benchmark_start) - Decimal("1")
            legacy: dict[str, Decimal | None] = {"return_5d": None, "return_20d": None, "return_60d": None}
            if prediction.horizon_days == 5:
                legacy["return_5d"] = value
            elif prediction.horizon_days == 20:
                legacy["return_20d"] = value
            elif prediction.horizon_days == 60:
                legacy["return_60d"] = value
            outcome = ForwardOutcome(
                prediction_id=prediction.prediction_id,
                observed_at=observed_at,
                benchmark_return=benchmark_return,
                terminal_price=terminal,
                return_at_horizon=value,
                benchmark_symbol=prediction.benchmark,
                outcome_source=source,
                price_timestamp=prediction.maturity_at if observations is not None else None,
                price_quality=quality,
                return_5d=legacy.get("return_5d"),
                return_20d=legacy.get("return_20d"),
                return_60d=legacy.get("return_60d"),
            )
            if self.append_outcome(outcome) == "APPENDED":
                appended.append(prediction.prediction_id)
        return {"status": "FORWARD_OUTCOME_INGESTED" if appended else "FORWARD_OUTCOME_NOT_READY", "appended": appended, "pending": pending, "missing_prices": missing, "pending_horizon_prices": unaligned, "authority": "SHADOW_EVIDENCE_ONLY", "policy_promotion": "NO_AUTOMATIC_PROMOTION"}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "predictions": [item.model_dump(mode="json") for item in self.predictions.values()],
            "outcomes": [item.model_dump(mode="json") for item in self.outcomes.values()],
        }
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        atomic_write(self.path, content)

    def evaluate(self, *, minimum_samples: int = 20, as_of: datetime | None = None) -> dict[str, object]:
        if minimum_samples < 1:
            raise ValueError("FORWARD_MINIMUM_SAMPLES_INVALID")
        cutoff = as_of or datetime.now(UTC)
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("FORWARD_EVALUATION_TIMEZONE_REQUIRED")
        rows: list[tuple[ForwardPrediction, ForwardOutcome, Decimal]] = []
        future_outcomes = sum(outcome.observed_at > cutoff for outcome in self.outcomes.values())
        for prediction_id, outcome in self.outcomes.items():
            if outcome.observed_at > cutoff:
                continue
            prediction = self.predictions[prediction_id]
            result = outcome.return_at_horizon
            if result is None:
                result = {5: outcome.return_5d, 20: outcome.return_20d, 60: outcome.return_60d}.get(prediction.horizon_days)
            if result is not None and outcome.benchmark_return is not None and outcome.price_quality == "VERIFIED_HORIZON_CLOSE":
                rows.append((prediction, outcome, result))
        by_horizon: dict[str, int] = {}
        for prediction, _, _ in rows:
            by_horizon[prediction.horizon_name] = by_horizon.get(prediction.horizon_name, 0) + 1
        reviewed_count = sum(outcome.close_evidence is not None for _, outcome, _ in rows)
        quality = {"reviewed_financial_sample_count": reviewed_count,
                   "reviewed_evaluation_readiness": "EVALUATION_ELIGIBLE" if reviewed_count >= minimum_samples else "INSUFFICIENT_EVIDENCE",
                   "sample_definition": "SYMBOL_HORIZON_ROWS_NOT_INDEPENDENT_PORTFOLIO_SAMPLES",
                   "legacy_sample_count": len(rows) - reviewed_count,
                   "financial_alpha_validated": False}
        if len(rows) < minimum_samples:
            return {"status": "INSUFFICIENT_FORWARD_EVIDENCE", "maturity_status": "PENDING_OBSERVATION_TIME" if future_outcomes else "PENDING_OUTCOMES" if len(self.outcomes) < len(self.predictions) else "OUTCOMES_RECORDED", "evaluation_cutoff": cutoff.isoformat(), "future_outcome_count": future_outcomes, "evaluation_readiness": "INSUFFICIENT_VERIFIED_SAMPLES", "unverified_outcome_count": len(self.outcomes) - len(rows) - future_outcomes, "sample_count": len(rows), "required": minimum_samples,
                    "prediction_count": len(self.predictions), "pending_count": len(self.predictions) - len(self.outcomes),
                    "by_horizon": by_horizon, "promotion_readiness": "NOT_ELIGIBLE_AUTOMATIC_PROMOTION_DISABLED", **quality}
        excess = [value - outcome.benchmark_return for _, outcome, value in rows if outcome.benchmark_return is not None]
        return {"status": "EVALUABLE_SHADOW_ONLY", "evaluation_cutoff": cutoff.isoformat(), "future_outcome_count": future_outcomes, "evaluation_readiness": "EVALUATION_ELIGIBLE", "authority": "SHADOW_EVIDENCE_ONLY", "policy_promotion": "NO_AUTOMATIC_PROMOTION", "sample_count": len(excess),
                "mean_excess_return": str(sum(excess, Decimal("0")) / len(excess)), "by_horizon": by_horizon,
                "promotion_readiness": "NOT_ELIGIBLE_AUTOMATIC_PROMOTION_DISABLED", **quality}


def policy_hash(policy: ForwardEvidencePolicy) -> str:
    return _hash(policy.model_dump(mode="json"))


def freeze_canonical_predictions(
    ledger: ForwardLedger,
    *,
    policy: ForwardEvidencePolicy,
    decision_run_id: str,
    decision_timestamp: datetime,
    information_cutoff: datetime,
    account_reference: str,
    universe: tuple[str, ...],
    prices: Mapping[str, Decimal],
    quant_scores: Mapping[str, Decimal],
    target_weights: Mapping[str, Decimal],
    order_signals: Mapping[str, str],
    cash_weight: Decimal,
    market_snapshot_hash: str,
    policy_digest: str,
    model_config_digest: str,
    research_available: bool,
    data_mode: str,
) -> dict[str, object]:
    """Freeze bounded per-symbol predictions from the already-final daily result.

    This function deliberately receives only the canonical decision inputs. It
    neither fetches data nor recalculates portfolio weights, so it cannot form a
    parallel source of trading truth.
    """
    if not policy.enabled:
        return {"status": "FORWARD_DISABLED", "frozen": [], "reason": "POLICY_DISABLED"}
    if data_mode == "FIXTURE":
        return {"status": "FORWARD_NOT_FROZEN", "frozen": [], "reason": "FIXTURE_NOT_FORWARD_EVIDENCE"}
    benchmark_price = prices.get(policy.benchmark)
    if benchmark_price is None or not benchmark_price.is_finite() or benchmark_price <= 0:
        return {"status": "FORWARD_NOT_FROZEN", "frozen": [], "reason": "BENCHMARK_PRICE_UNAVAILABLE"}
    local = information_cutoff.astimezone(NEW_YORK)
    trading_session = local.date() if is_trading_session(local) else latest_completed_session(information_cutoff)
    mode = ForwardMode.QUANT_PLUS_LLM if research_available else ForwardMode.PURE_QUANT
    if mode.value not in policy.allowed_modes:
        return {"status": "FORWARD_NOT_FROZEN", "frozen": [], "reason": "MODE_NOT_ALLOWED_BY_POLICY"}
    frozen: list[str] = []
    existing: list[str] = []
    exposure = Decimal("1") - cash_weight
    for symbol in sorted(set(universe)):
        price = prices.get(symbol)
        if price is None or not price.is_finite() or price <= 0:
            continue
        quant_score = quant_scores.get(symbol, Decimal("0"))
        signal = order_signals.get(symbol, "TARGET" if target_weights.get(symbol, Decimal("0")) > 0 else "HOLD")
        for horizon in policy.horizons:
            authority_key = _hash({
                "account": account_reference,
                "session": trading_session.isoformat(),
                "symbol": symbol,
                "horizon": horizon.name,
                "policy_hash": policy_digest,
                "mode": mode.value,
            })
            prediction = ForwardPrediction(
                prediction_id="forward-" + authority_key[:24],
                authority_key=authority_key,
                decision_run_id=decision_run_id,
                decision_timestamp=decision_timestamp,
                information_cutoff=information_cutoff,
                trading_session=trading_session,
                maturity_session=advance_sessions(trading_session, horizon.trading_sessions),
                horizon_name=horizon.name,
                horizon_days=horizon.trading_sessions,
                symbol=symbol,
                price=price,
                benchmark=policy.benchmark,
                benchmark_price=benchmark_price,
                universe=tuple(sorted(set(universe))),
                mode=mode,
                quant_score=quant_score,
                llm_score=None,
                combined_research_score=quant_score,
                signal=signal,
                target_weight=target_weights.get(symbol, Decimal("0")),
                exposure=exposure,
                model="deterministic-operational-signal",
                provider="canonical-daily",
                prompt_version="NOT_APPLICABLE" if not research_available else "ADVISORY_CONTEXT_ONLY",
                software_version="meridian-forward-v2",
                policy_hash=policy_digest,
                model_config_hash=model_config_digest,
                market_snapshot_hash=market_snapshot_hash,
                source_status="OPERATIONAL_PUBLIC_NOT_CERTIFIED",
            )
            result = ledger.append_prediction(prediction)
            (frozen if result == "APPENDED" else existing).append(prediction.prediction_id)
    return {"status": "FORWARD_FROZEN" if frozen or existing else "FORWARD_NOT_FROZEN", "frozen": frozen,
            "existing": existing, "mode": mode.value, "trading_session": trading_session.isoformat()}
