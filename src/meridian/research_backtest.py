"""Isolated point-in-time research evaluation; never a portfolio simulator."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import Field

from meridian.daily_research import ResearchFailureStatus
from meridian.schemas import StableModel
from meridian.temporal import ResearchTemporalContext


class HistoricalDecision(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    direction: str = Field(pattern=r"^(BULLISH|BEARISH|NEUTRAL)$")
    confidence: Decimal = Field(ge=0, le=1)
    decision_status: ResearchFailureStatus
    research_status: str
    evidence_ids: tuple[str, ...] = ()
    evidence_coverage: Decimal = Field(ge=0, le=1)
    disagreement_score: Decimal | None = Field(default=None, ge=0, le=1)


class HistoricalOutcome(StableModel):
    forward_return: Decimal
    benchmark_return: Decimal | None = None


class BacktestCell(StableModel):
    run_id: str
    symbol: str
    analysis_date: date
    holding_period_days: int = Field(gt=0)
    context: ResearchTemporalContext
    decision: HistoricalDecision
    outcome: HistoricalOutcome | None = None
    direction_correct: bool | None = None


def date_grid(start: date, end: date, *, every_n_days: int = 1) -> tuple[date, ...]:
    if every_n_days < 1 or end < start:
        raise ValueError("BACKTEST_DATE_GRID_INVALID")
    values = []
    cursor = start
    while cursor <= end:
        values.append(cursor)
        cursor += timedelta(days=every_n_days)
    return tuple(values)


class ResearchBacktestRunner:
    """Run independent historical cells into an explicitly isolated directory."""

    def __init__(
        self,
        root: Path,
        evaluator: Callable[[str, ResearchTemporalContext], HistoricalDecision],
        outcome_loader: Callable[[str, date, int], HistoricalOutcome | None],
    ) -> None:
        self.root = root.resolve()
        self.evaluator = evaluator
        self.outcome_loader = outcome_loader

    def run(
        self,
        *,
        run_id: str,
        symbols: Iterable[str],
        dates: Iterable[date],
        holding_period_days: int,
        resume: bool = True,
    ) -> dict[str, object]:
        if not run_id or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for char in run_id
        ):
            raise ValueError("BACKTEST_RUN_ID_INVALID")
        if holding_period_days < 1:
            raise ValueError("BACKTEST_HOLDING_PERIOD_INVALID")
        directory = (self.root / "backtests" / run_id).resolve()
        if self.root not in directory.parents:
            raise ValueError("BACKTEST_PATH_ESCAPE")
        directory.mkdir(parents=True, exist_ok=True)
        decision_log = directory / "decision_log.jsonl"
        completed = self._completed(decision_log) if resume else set()
        cells = []
        for symbol in sorted({item.upper() for item in symbols}):
            for analysis_date in sorted(set(dates)):
                key = (symbol, analysis_date.isoformat())
                if key in completed:
                    continue
                cutoff = datetime.combine(analysis_date, datetime.max.time(), tzinfo=UTC)
                context = ResearchTemporalContext(
                    run_id=f"{run_id}-{symbol}-{analysis_date.isoformat()}",
                    trading_date=analysis_date,
                    as_of=cutoff,
                    information_cutoff=cutoff,
                    market_session="HISTORICAL_REPLAY",
                    timezone="UTC",
                )
                decision = self.evaluator(symbol, context)
                outcome = self.outcome_loader(symbol, analysis_date, holding_period_days)
                correct = self._correct(decision.direction, outcome)
                cell = BacktestCell(
                    run_id=run_id,
                    symbol=symbol,
                    analysis_date=analysis_date,
                    holding_period_days=holding_period_days,
                    context=context,
                    decision=decision,
                    outcome=outcome,
                    direction_correct=correct,
                )
                self._append(decision_log, cell.model_dump(mode="json"))
                self._append(directory / "calibration.jsonl", self._calibration(cell))
                cells.append(cell)
        summary = self.summarize(decision_log)
        (directory / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return {**summary, "cells_run": len(cells), "directory": str(directory)}

    @staticmethod
    def _completed(path: Path) -> set[tuple[str, str]]:
        if not path.is_file():
            return set()
        completed = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                completed.add((str(row["symbol"]), str(row["analysis_date"])))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return completed

    @staticmethod
    def _append(path: Path, row: dict[str, object]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    @staticmethod
    def _correct(direction: str, outcome: HistoricalOutcome | None) -> bool | None:
        if outcome is None or direction == "NEUTRAL":
            return None
        return outcome.forward_return > 0 if direction == "BULLISH" else outcome.forward_return < 0

    @staticmethod
    def _calibration(cell: BacktestCell) -> dict[str, object]:
        return {
            "run_id": cell.run_id,
            "symbol": cell.symbol,
            "date": cell.analysis_date.isoformat(),
            "direction": cell.decision.direction,
            "confidence": str(cell.decision.confidence),
            "holding_period_days": cell.holding_period_days,
            "forward_return": str(cell.outcome.forward_return) if cell.outcome else None,
            "direction_correct": cell.direction_correct,
            "evidence_coverage": str(cell.decision.evidence_coverage),
            "research_status": cell.decision.research_status,
            "decision_status": cell.decision.decision_status.value,
            "disagreement_score": str(cell.decision.disagreement_score)
            if cell.decision.disagreement_score is not None
            else None,
        }

    @staticmethod
    def summarize(path: Path) -> dict[str, object]:
        rows = (
            [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            if path.is_file()
            else []
        )
        settled = [row for row in rows if row.get("direction_correct") is not None]
        reviews = [
            row
            for row in rows
            if row["decision"]["decision_status"] == ResearchFailureStatus.REVIEW_REQUIRED.value
        ]
        stale = [
            row
            for row in rows
            if row["decision"]["decision_status"] == ResearchFailureStatus.STALE_EVIDENCE.value
        ]
        failures = [
            row
            for row in rows
            if row["decision"]["decision_status"] != ResearchFailureStatus.VALID.value
        ]
        return {
            "cells": len(rows),
            "settled": len(settled),
            "directional_accuracy": (
                sum(bool(row["direction_correct"]) for row in settled) / len(settled)
            )
            if settled
            else None,
            "coverage": (
                sum(float(row["decision"]["evidence_coverage"]) for row in rows) / len(rows)
            )
            if rows
            else 0.0,
            "failure_rate": len(failures) / len(rows) if rows else 0.0,
            "review_required_rate": len(reviews) / len(rows) if rows else 0.0,
            "stale_data_rejection_rate": len(stale) / len(rows) if rows else 0.0,
        }
