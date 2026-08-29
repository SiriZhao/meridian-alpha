"""Sanitized record/replay store for normalized research outcomes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from meridian.research import PointInTimeStatus, ResearchMode, ResearchOutcome


class ResearchReplayStore:
    schema_version = "1"

    def __init__(self, directory: Path):
        self.directory = directory

    def record(self, outcome: ResearchOutcome) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{outcome.ticker}-{outcome.as_of.strftime('%Y%m%dT%H%M%SZ')}.json"
        payload = {
            "schema_version": self.schema_version,
            "ticker": outcome.ticker,
            "as_of": outcome.as_of.isoformat(),
            "outcome": outcome.model_dump(mode="json"),
        }
        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        return path

    def load(self, ticker: str, as_of: datetime) -> ResearchOutcome:
        path = self.directory / f"{ticker}-{as_of.strftime('%Y%m%dT%H%M%SZ')}.json"
        if not path.is_file():
            raise FileNotFoundError(path.name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != self.schema_version:
            raise ValueError("unsupported replay schema version")
        outcome = ResearchOutcome.model_validate(payload.get("outcome"))
        if outcome.ticker != ticker or outcome.as_of != as_of:
            raise ValueError("replay fixture identity mismatch")
        if outcome.mode is not ResearchMode.REPLAY or outcome.point_in_time_status is not PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE:
            outcome = outcome.model_copy(
                update={
                    "mode": ResearchMode.REPLAY,
                    "point_in_time_status": PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE,
                }
            )
        return outcome
