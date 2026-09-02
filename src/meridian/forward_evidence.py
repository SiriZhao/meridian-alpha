"""Append-only forward-prediction evidence; mature outcomes never rewrite predictions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from meridian.schemas import StableModel


class ForwardPrediction(StableModel):
    prediction_id: str
    decision_timestamp: datetime
    information_cutoff: datetime
    symbol: str
    price: Decimal
    quant_score: Decimal
    llm_score: Decimal | None = None
    combined_research_score: Decimal
    model: str
    provider: str
    prompt_version: str
    software_version: str
    horizon_days: int

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class ForwardOutcome(StableModel):
    prediction_id: str
    observed_at: datetime
    return_5d: Decimal | None = None
    return_20d: Decimal | None = None
    return_60d: Decimal | None = None
    benchmark_return: Decimal | None = None
    max_adverse_excursion: Decimal | None = None
    max_favorable_excursion: Decimal | None = None


class ForwardLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.predictions: dict[str, ForwardPrediction] = {}
        self.outcomes: dict[str, ForwardOutcome] = {}
        if path.is_file():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for item in raw.get("predictions", []):
            prediction = ForwardPrediction.model_validate(item)
            self.predictions[prediction.prediction_id] = prediction
        for item in raw.get("outcomes", []):
            outcome = ForwardOutcome.model_validate(item)
            self.outcomes[outcome.prediction_id] = outcome

    def append_prediction(self, prediction: ForwardPrediction) -> None:
        previous = self.predictions.get(prediction.prediction_id)
        if previous and previous.content_hash != prediction.content_hash:
            raise ValueError("FORWARD_PREDICTION_IMMUTABLE")
        self.predictions[prediction.prediction_id] = prediction
        self._write()

    def append_outcome(self, outcome: ForwardOutcome) -> None:
        prediction = self.predictions.get(outcome.prediction_id)
        if prediction is None:
            raise ValueError("FORWARD_PREDICTION_UNKNOWN")
        if outcome.observed_at < prediction.information_cutoff + timedelta(days=prediction.horizon_days):
            raise ValueError("FORWARD_OUTCOME_NOT_MATURE")
        if outcome.prediction_id in self.outcomes:
            raise ValueError("FORWARD_OUTCOME_IMMUTABLE")
        self.outcomes[outcome.prediction_id] = outcome
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": "forward-evidence.v1", "predictions": [item.model_dump(mode="json") for item in self.predictions.values()], "outcomes": [item.model_dump(mode="json") for item in self.outcomes.values()]}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.path)

    def evaluate(self) -> dict[str, object]:
        mature = [self.outcomes[key] for key in self.outcomes if self.outcomes[key].return_20d is not None]
        if len(mature) < 20:
            return {"status": "INSUFFICIENT_FORWARD_EVIDENCE", "sample_count": len(mature), "required": 20}
        excess = [item.return_20d - (item.benchmark_return or Decimal("0")) for item in mature if item.return_20d is not None]
        return {"status": "EVALUABLE_SHADOW_ONLY", "sample_count": len(excess), "mean_excess_return": str(sum(excess, Decimal("0")) / len(excess))}
