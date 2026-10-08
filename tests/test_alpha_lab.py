"""Synthetic fixtures prove contracts, never financial alpha."""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from meridian.alpha_lab import (
    LabBar,
    LabInput,
    TemporalLabel,
    challenger_scores,
    lab_report,
    operational_score,
    purged_training_indices,
    render_lab_report,
    require_lab_path,
)
from meridian.dated_close import (
    CloseStatus,
    CorporateAction,
    DatedClose,
    ReviewedPricePair,
    append_reviewed_pair,
    evaluate_close,
    holding_period_return,
    ingest_reviewed_outcome,
    load_reviewed_pairs,
    reconcile_closes,
)
from meridian.forward_evidence import ForwardLedger, ForwardPrediction, advance_sessions
from meridian.trading_calendar import is_trading_session, session_close

START = date(2026, 10, 7)
NOW = session_close(START)


def prediction() -> ForwardPrediction:
    return ForwardPrediction(prediction_id="review-fixture", decision_timestamp=NOW,
        information_cutoff=NOW, symbol="AAPL", price=Decimal("100"), quant_score=Decimal(".01"),
        combined_research_score=Decimal(".01"), model="fixture", provider="fixture", prompt_version="fixture",
        software_version="fixture", horizon_days=5, trading_session=START,
        maturity_session=advance_sessions(START, 5), benchmark_price=Decimal("500"))


def pair() -> ReviewedPricePair:
    pred = prediction()
    assert pred.maturity_session is not None
    received = pred.maturity_at + timedelta(hours=1)
    closes = [DatedClose(symbol=symbol, session_date=pred.maturity_session,
              close_basis="DEFINED_UNADJUSTED_SESSION_CLOSE", price=Decimal(price), source="review-fixture",
              source_timestamp=pred.maturity_at, available_at=received, ingested_at=received,
              origin="HUMAN_REVIEWED_LOCAL", adjustment_status="UNADJUSTED")
              for symbol, price in (("AAPL", "110"), ("SPY", "510"))]
    result = ReviewedPricePair(prediction=pred, terminal=closes[0], benchmark_terminal=closes[1],
        corporate_action_basis="UNADJUSTED_SHARE_AND_CASH_HOLDING_PERIOD",
        inception_basis="UNADJUSTED_DECISION_PRICE", inception_evidence_origin="REVIEWED_LOCAL", action_coverage_complete=True)
    return review(result)


def review(value: ReviewedPricePair) -> ReviewedPricePair:
    return value.model_copy(update={"reviewed_digest": value.evidence_digest,
        "reviewer_reference": "TEST_RECEIPT_NOT_REAL_FINANCIAL_EVIDENCE", "reviewed_at": value.terminal.ingested_at + timedelta(minutes=1)})


def test_reviewed_close_persists_immutable_outcome_and_revalidates(tmp_path: Path) -> None:
    value = pair()
    path = tmp_path / "alpha-lab" / "forward.json"
    ledger = ForwardLedger(path)
    ledger.append_prediction(value.prediction)
    result = ingest_reviewed_outcome(ledger, value, as_of=value.prediction.maturity_at + timedelta(days=1))
    assert result.validation_status is CloseStatus.VERIFIED
    assert result.return_at_horizon == Decimal(".1") and result.benchmark_return == Decimal(".02")
    before = path.read_bytes()
    ingest_reviewed_outcome(ledger, value, as_of=value.prediction.maturity_at + timedelta(days=2))
    assert path.read_bytes() == before
    restored = ForwardLedger(path)
    assert len(restored.outcomes) == 1
    assert restored.evaluate(minimum_samples=1, as_of=value.prediction.maturity_at + timedelta(days=1))["reviewed_financial_sample_count"] == 1
    assert result.quote_certification == "BLOCKED" and result.automatic_promotion == "DISABLED"
    raw = json.loads(path.read_text())
    raw["outcomes"][0]["return_at_horizon"] = "0.9"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="PROVENANCE_MISMATCH"):
        ForwardLedger(path)


@pytest.mark.parametrize("origin", ["PUBLIC_DOWNLOAD", "SYNTHETIC_FIXTURE"])
def test_public_and_synthetic_closes_never_verify(origin: str, tmp_path: Path) -> None:
    value = pair()
    value = review(value.model_copy(update={"terminal": value.terminal.model_copy(update={"origin": origin})}))
    ledger = ForwardLedger(tmp_path / "alpha-lab" / "forward.json")
    ledger.append_prediction(value.prediction)
    result = ingest_reviewed_outcome(ledger, value, as_of=value.prediction.maturity_at + timedelta(days=1))
    assert result.validation_status is CloseStatus.PUBLIC
    assert result.return_at_horizon is None and not ledger.outcomes


@pytest.mark.parametrize(("change", "status"), [
    ({"action_coverage_complete": False}, CloseStatus.ADJUSTMENT_UNKNOWN),
    ({"reviewed_digest": "0" * 64}, CloseStatus.PUBLIC),
    ({"reviewer_reference": None}, CloseStatus.PUBLIC),
    ({"inception_evidence_origin": "SYNTHETIC_FIXTURE"}, CloseStatus.PUBLIC),
    ({"reviewed_at": NOW}, CloseStatus.CONFLICT),
])
def test_review_boundaries(change: dict[str, object], status: CloseStatus) -> None:
    value = pair().model_copy(update=change)
    result = evaluate_close(value, as_of=value.prediction.maturity_at + timedelta(days=1))
    assert result.validation_status is status and result.return_at_horizon is None


@pytest.mark.parametrize(("kind", "ratio", "cash", "terminal", "expected"), [
    ("SPLIT", "2", None, "50", "0"),
    ("REVERSE_SPLIT", ".5", None, "200", "0"),
    ("CASH_DIVIDEND", None, "2", "98", "0"),
    ("SPECIAL_DIVIDEND", None, "20", "80", "0"),
])
def test_share_and_cash_return_basis(kind: str, ratio: str | None, cash: str | None, terminal: str, expected: str) -> None:
    action = CorporateAction.model_validate({"kind": kind, "effective_at": NOW + timedelta(days=1),
        "available_at": NOW, "source": "fixture", "ratio": ratio, "cash_per_share": cash})
    assert holding_period_return(Decimal("100"), Decimal(terminal), (action,)) == Decimal(expected)


@pytest.mark.parametrize("kind", ["SYMBOL_CHANGE", "SUSPENSION", "DELISTING"])
def test_unresolved_action_cannot_generate_return(kind: str) -> None:
    value = pair()
    action = CorporateAction.model_validate({"kind": kind, "effective_at": NOW + timedelta(days=1), "available_at": NOW, "source": "fixture"})
    value = review(value.model_copy(update={"actions": (action,)}))
    result = evaluate_close(value, as_of=value.prediction.maturity_at + timedelta(days=1))
    assert result.validation_status is CloseStatus.UNSUPPORTED_ACTION
    assert result.return_at_horizon is None


def test_adjustment_receipt_binds_actions_and_counts_shares() -> None:
    value = pair()
    split = CorporateAction(kind="SPLIT", effective_at=NOW + timedelta(days=1), available_at=NOW, source="fixture", ratio=Decimal("2"))
    dividend = CorporateAction(kind="CASH_DIVIDEND", effective_at=NOW + timedelta(days=2), available_at=NOW, source="fixture", cash_per_share=Decimal("1"))
    changed = value.model_copy(update={"actions": (split, dividend), "terminal": value.terminal.model_copy(update={"price": Decimal("54")})})
    assert evaluate_close(changed, as_of=value.prediction.maturity_at + timedelta(days=1)).validation_status is CloseStatus.PUBLIC
    result = evaluate_close(review(changed), as_of=value.prediction.maturity_at + timedelta(days=1))
    assert result.return_at_horizon == Decimal(".1")
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        holding_period_return(Decimal("100"), Decimal("54"), (split, split))


def test_maturity_delayed_publication_and_missingness() -> None:
    value = pair()
    assert evaluate_close(value, as_of=NOW).validation_status is CloseStatus.NOT_MATURE
    assert evaluate_close(value, as_of=value.prediction.maturity_at).validation_status is CloseStatus.MISSING
    result = reconcile_closes((value.prediction,), (), as_of=value.prediction.maturity_at)
    assert result["MATURED"] == result["MISSING"] == 1
    assert result["VERIFIED"] == 0 and not result["EVALUATION_ELIGIBLE"]
    assert reconcile_closes((value.prediction,), (), as_of=NOW)["PENDING"] == 1


@pytest.mark.parametrize("year", [2020, 2025, 2029])
def test_unreviewed_historical_calendar_rejected(year: int) -> None:
    close = pair().terminal.model_dump(mode="json")
    close["session_date"] = f"{year}-10-07"
    with pytest.raises(ValueError, match="CALENDAR_SCOPE"):
        DatedClose.model_validate(close)


@pytest.mark.parametrize("field", ["source_timestamp", "available_at", "ingested_at"])
def test_corrupt_timestamp_rejected(field: str) -> None:
    close = pair().terminal.model_dump(mode="json")
    close[field] = NOW.isoformat()
    with pytest.raises(ValueError):
        DatedClose.model_validate(close)


def test_archive_crash_retry_and_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "alpha-lab" / "closes.json"
    value = pair()
    import meridian.dated_close as module
    original = module.atomic_write
    def crash(path: Path, content: str | bytes) -> None:
        raise OSError("injected before replace")
    monkeypatch.setattr(module, "atomic_write", crash)
    with pytest.raises(OSError):
        append_reviewed_pair(path, value)
    assert not path.exists()
    monkeypatch.setattr(module, "atomic_write", original)
    assert append_reviewed_pair(path, value) == "APPENDED"
    assert append_reviewed_pair(path, value) == "EXISTS"
    assert load_reviewed_pairs(path) == (value,)
    with pytest.raises(ValueError, match="IMMUTABLE"):
        append_reviewed_pair(path, value.model_copy(update={"reviewer_reference": "changed"}))


def test_close_archive_parallel_process_contention_and_safe_retry(tmp_path: Path) -> None:
    import subprocess
    import sys

    from meridian.runtime_io import run_lock
    path = tmp_path / "alpha-lab" / "closes.json"
    path.parent.mkdir()
    source = path.parent / "input.json"
    source.write_text(pair().stable_json(), encoding="utf-8")
    command = [sys.executable, "-c", "from pathlib import Path; import sys; from meridian.dated_close import ReviewedPricePair, append_reviewed_pair; p=ReviewedPricePair.model_validate_json(Path(sys.argv[1]).read_text()); append_reviewed_pair(Path(sys.argv[2]),p)", str(source), str(path)]
    with run_lock(path.parent / ".close-locks", "parent-fixture", name="dated-close"):
        blocked = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert blocked.returncode != 0 and not path.exists()
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert load_reviewed_pairs(path) == (pair(),)


@pytest.mark.parametrize("content", ["", "null", "{}", '{"schema_version":"meridian-dated-close.v1","pairs":[{}]}'])
def test_corrupt_close_archive_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "alpha-lab" / "closes.json"
    path.parent.mkdir()
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_reviewed_pairs(path)


@pytest.mark.parametrize(("start", "horizon", "expected"), [
    (date(2026, 3, 6), 5, date(2026, 3, 13)),
    (date(2026, 7, 2), 1, date(2026, 7, 6)),
    (date(2026, 11, 20), 5, date(2026, 11, 30)),
    (date(2026, 10, 30), 5, date(2026, 11, 6)),
])
def test_horizon_holiday_and_dst_session_alignment(start: date, horizon: int, expected: date) -> None:
    assert advance_sessions(start, horizon) == expected
    if start == date(2026, 3, 6):
        assert session_close(start).hour == 21 and session_close(expected).hour == 20
    if start == date(2026, 10, 30):
        assert session_close(start).hour == 20 and session_close(expected).hour == 21


@pytest.mark.parametrize("path", ["E:/MeridianAlphaRuntime/alpha-lab/outcomes.json", "ordinary/outcomes.json", "alpha-lab/meridian.sqlite3"])
def test_canonical_and_nonlab_writes_forbidden(path: str) -> None:
    with pytest.raises(ValueError):
        require_lab_path(Path(path))


def lab_input() -> LabInput:
    dates = [START]
    while len(dates) < 21:
        previous = dates[-1] - timedelta(days=1)
        while not is_trading_session(previous):
            previous -= timedelta(days=1)
        dates.append(previous)
    return LabInput(symbol="AAPL", as_of=NOW, daily_return=Decimal(".05"), daily_return_available_at=NOW,
        bars=tuple(LabBar(timestamp=session_close(day), available_at=session_close(day),
            close=Decimal(100 + i), source="synthetic", adjustment_basis="CONSISTENT_REVIEWED") for i, day in enumerate(reversed(dates))), evidence_origin="SYNTHETIC_FIXTURE")


def test_challengers_reproducible_missing_research_contributes_zero() -> None:
    data = lab_input()
    result = challenger_scores(data)
    assert result[0].score == 0 and result[1].score == Decimal(".05")
    assert result[2].status == "AVAILABLE" and result[2].factors["momentum_20"] == Decimal(".2")
    assert result[3].score == result[1].score and result[3].research_contribution == 0
    with localcontext() as context:
        context.prec = 10
        assert challenger_scores(data) == result
    report = lab_report(data)
    assert report["evaluation_status"] == "NOT_EVALUABLE" and report["financial_sample_count"] == 0
    assert report["model_invocations"] == 0 and report["broker_submission"] == "DISABLED"
    markdown = render_lab_report(report)
    recovered = json.loads(markdown.split("```json\n")[1].split("\n```")[0])
    assert recovered == report


def test_history_and_label_cutoff_fail_closed() -> None:
    data = lab_input()
    raw = data.model_dump(mode="json")
    raw["bars"][-1]["available_at"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="AFTER_CUTOFF"):
        LabInput.model_validate(raw)
    assert challenger_scores(data.model_copy(update={"bars": ()}))[2].score is None
    labels = tuple(TemporalLabel(decision_at=NOW - timedelta(days=10), mature_at=NOW - timedelta(days=2), available_at=available)
                   for available in (NOW - timedelta(days=1), NOW, NOW + timedelta(days=1)))
    assert purged_training_indices(labels, test_start=NOW) == (0,)


@pytest.mark.parametrize("value", ["-.5", "0", ".01", "2"])
def test_baseline_score_semantics(value: str) -> None:
    assert operational_score(Decimal(value)) == max(Decimal("0"), Decimal(value))




def test_signal_evaluation_requires_predeclared_experiment_and_rejects_fixture() -> None:
    from meridian.lab_evaluation import evaluate_signals
    value = pair()
    data = LabInput(symbol="AAPL", as_of=NOW, daily_return=Decimal(".01"), daily_return_available_at=NOW, evidence_origin="SYNTHETIC_FIXTURE")
    result = evaluate_signals((data,), (value,), as_of=value.prediction.maturity_at + timedelta(days=1),
        registered_at=NOW, universe=("AAPL",), universe_available_at=NOW)
    assert result["status"] == "INSUFFICIENT_EVIDENCE" and result["metrics"] is None
    assert result["temporal_blocks"] == 0 and result["conclusion"] == "NO_DEMONSTRATED_ALPHA"
    with pytest.raises(ValueError, match="NOT_PREDECLARED"):
        evaluate_signals((data,), (value,), as_of=value.prediction.maturity_at + timedelta(days=1),
            registered_at=NOW + timedelta(seconds=1), universe=("AAPL",), universe_available_at=NOW)


def evaluation_fixtures(starts: tuple[date, ...]) -> tuple[tuple[LabInput, ...], tuple[ReviewedPricePair, ...]]:
    inputs, pairs = [], []
    template = pair()
    for index, start in enumerate(starts):
        decision, maturity = session_close(start), session_close(advance_sessions(start, 5))
        received = maturity + timedelta(hours=1)
        for number, symbol in enumerate(("AAPL", "MSFT", "NVDA"), 1):
            pred = template.prediction.model_copy(update={"prediction_id": f"test-{index}-{symbol}", "symbol": symbol,
                "decision_timestamp": decision, "information_cutoff": decision, "trading_session": start,
                "maturity_session": advance_sessions(start, 5), "quant_score": Decimal(number) / 100})
            terminal = DatedClose(symbol=symbol, session_date=advance_sessions(start, 5), close_basis="DEFINED_UNADJUSTED_SESSION_CLOSE",
                price=Decimal(100 + number * 5), source="TEST_MOCK_REVIEW_NOT_REAL_DATA", source_timestamp=maturity,
                available_at=received, ingested_at=received, origin="HUMAN_REVIEWED_LOCAL", adjustment_status="UNADJUSTED")
            benchmark = terminal.model_copy(update={"symbol": "SPY", "price": Decimal("510")})
            value = review(template.model_copy(update={"prediction": pred, "terminal": terminal, "benchmark_terminal": benchmark}))
            pairs.append(value)
            inputs.append(LabInput(symbol=symbol, as_of=decision, daily_return=Decimal(number) / 100,
                daily_return_available_at=decision, evidence_origin="REVIEWED_RESEARCH"))
    return tuple(inputs), tuple(pairs)


def test_descriptive_evaluation_has_common_blocks_and_no_false_alpha() -> None:
    from meridian.lab_evaluation import evaluate_signals
    starts = (START, advance_sessions(START, 6), advance_sessions(START, 12))
    inputs, pairs = evaluation_fixtures(starts)
    result = evaluate_signals(inputs, pairs, as_of=pairs[-1].prediction.maturity_at + timedelta(days=1),
        registered_at=NOW - timedelta(days=1), universe=("AAPL", "MSFT", "NVDA"), universe_available_at=NOW - timedelta(days=2), minimum_temporal_blocks=3)
    assert result["status"] == "DESCRIPTIVE_SIGNAL_EVALUATION_ONLY" and result["temporal_blocks"] == 3
    assert result["conclusion"] == "NO_DEMONSTRATED_ALPHA" and result["llm_comparison_status"] == "INSUFFICIENT_EVIDENCE"
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["PURE_QUANT"]["mean_cross_sectional_ic"] == "1"
    assert metrics["PURE_QUANT"] == metrics["QUANT_PLUS_LLM"]
    assert result["portfolio_metrics"] == "NOT_EVALUABLE"


def test_evaluation_purges_overlap_and_requires_complete_universe() -> None:
    from meridian.lab_evaluation import evaluate_signals
    inputs, pairs = evaluation_fixtures((START, advance_sessions(START, 1), advance_sessions(START, 6)))
    common = {"as_of": pairs[-1].prediction.maturity_at + timedelta(days=1), "registered_at": NOW - timedelta(days=1),
              "universe": ("AAPL", "MSFT", "NVDA"), "universe_available_at": NOW - timedelta(days=2), "minimum_temporal_blocks": 3}
    result = evaluate_signals(inputs, pairs, **common)
    assert result["purged_overlapping_rows"] == 3 and result["temporal_blocks"] == 2
    assert result["status"] == "INSUFFICIENT_EVIDENCE" and result["metrics"] is None
    missing = evaluate_signals(inputs, pairs[:-1], **common)
    assert missing["incomplete_universe_rows"] == 2 and missing["temporal_blocks"] == 1


@pytest.mark.parametrize(("scores", "returns", "expected"), [
    (["1", "2", "3"], ["1", "2", "3"], "1"),
    (["1", "2", "3"], ["3", "2", "1"], "-1"),
    (["1", "1", "1"], ["1", "2", "3"], None),
    (["1", "2"], ["1", "2"], None),
])
def test_rank_correlation_degenerate_and_directional_cases(scores: list[str], returns: list[str], expected: str | None) -> None:
    from meridian.lab_evaluation import rank_correlation
    result = rank_correlation([Decimal(value) for value in scores], [Decimal(value) for value in returns])
    assert result == (Decimal(expected) if expected is not None else None)







