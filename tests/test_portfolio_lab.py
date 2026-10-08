"""Mock review receipts validate arithmetic, never demonstrate market alpha."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, Inexact, localcontext
from pathlib import Path

import pytest

from meridian.alpha_lab import LabBar
from meridian.config import load_policies
from meridian.portfolio_lab import PortfolioExperiment, evaluate_portfolios, round_trip_return
from meridian.trading_calendar import is_trading_session, session_close
from tests.test_alpha_lab import NOW, START, evaluation_fixtures


def dataset():
    from meridian.forward_evidence import advance_sessions
    inputs, pairs = evaluation_fixtures(tuple(advance_sessions(START, 6 * i) if i else START for i in range(6)))
    enriched = []
    for data in inputs:
        day = data.as_of.date()
        days = []
        while len(days) < 21:
            if is_trading_session(day):
                days.append(day)
            day -= timedelta(days=1)
        bars = tuple(LabBar(timestamp=session_close(day), available_at=session_close(day), close=Decimal(100 + i),
            source="SYNTHETIC_MOCK_REVIEW_NOT_MARKET_DATA", adjustment_basis="CONSISTENT_REVIEWED") for i, day in enumerate(reversed(days)))
        enriched.append(data.model_copy(update={"bars": bars}))
    policy = load_policies(Path(__file__).parents[1] / "policies").risk
    times = sorted({data.as_of for data in enriched})
    experiment = PortfolioExperiment(experiment_id="MOCK_REVIEW_FIXTURE_ONLY", registered_at=NOW - timedelta(days=1),
        universe=("AAPL", "MSFT", "NVDA"), universe_available_at=NOW - timedelta(days=2), validation_start=times[1],
        test_start=times[2], evaluation_at=pairs[-1].prediction.maturity_at + timedelta(days=1), risk_policy=policy, minimum_test_blocks=2)
    return tuple(enriched), pairs, experiment


def test_roundtrip_accounts_for_entry_exit_fees_and_cash() -> None:
    net, costs, turnover = round_trip_return({"A": Decimal(".5")}, {"A": Decimal(".1")}, cost_bps=Decimal("100"))
    assert net == Decimal(".0395") and costs == Decimal(".0105") and turnover == Decimal("1.05")
    assert round_trip_return({}, {}, cost_bps=Decimal("100")) == (0, 0, 0)


@pytest.mark.parametrize(("weights", "returns", "cost"), [
    ({"A": Decimal("1")}, {"A": Decimal(".1")}, Decimal("1")),
    ({"A": Decimal("-.1")}, {"A": Decimal(".1")}, Decimal("0")),
    ({"A": Decimal(".5")}, {}, Decimal("0")),
    ({"A": Decimal(".5")}, {"A": Decimal("-1.1")}, Decimal("0")),
    ({}, {}, Decimal("NaN")),
])
def test_roundtrip_rejects_insolvent_missing_or_nonfinite_inputs(weights, returns, cost) -> None:
    with pytest.raises(ValueError):
        round_trip_return(weights, returns, cost_bps=cost)


def test_common_oos_cost_grid_reproducible_under_caller_decimal_context() -> None:
    inputs, pairs, experiment = dataset()
    first = evaluate_portfolios(inputs, pairs, experiment=experiment)
    with localcontext() as context:
        context.prec = 8
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        assert evaluate_portfolios(tuple(reversed(inputs)), tuple(reversed(pairs)), experiment=experiment) == first
    assert first["partition_blocks"] == {"TRAIN": 1, "VALIDATION": 1, "TEST": 4}
    assert first["conclusion"] == "NO_DEMONSTRATED_ALPHA"
    assert first["llm_comparison_status"] == "INSUFFICIENT_EVIDENCE"
    metrics = first["metrics"]
    assert isinstance(metrics, dict)
    low, high = metrics["0"], metrics["20"]
    assert low["CASH"]["cumulative_return"] == "0"
    assert Decimal(low["OPERATIONAL_QUANT"]["cumulative_return"]) > Decimal(high["OPERATIONAL_QUANT"]["cumulative_return"])
    assert low["OPERATIONAL_QUANT"] == low["QUANT_PLUS_LLM"]
    assert first["broker_submission"] == "DISABLED" and first["automatic_promotion"] == "DISABLED"
    assert len(low["OPERATIONAL_QUANT"]["periods"]) == 4
    assert all(row["target_weights"] for row in low["OPERATIONAL_QUANT"]["periods"])


def test_fixture_public_missing_cohort_never_generates_portfolio_statistics() -> None:
    inputs, pairs, experiment = dataset()
    synthetic = tuple(data.model_copy(update={"evidence_origin": "SYNTHETIC_FIXTURE"}) for data in inputs)
    result = evaluate_portfolios(synthetic, pairs, experiment=experiment)
    assert result["status"] == "INSUFFICIENT_EVIDENCE" and result["metrics"] is None
    result = evaluate_portfolios(inputs, pairs[:-1], experiment=experiment.model_copy(update={"minimum_test_blocks": 4}))
    assert result["rejected_blocks"] == {"INCOMPLETE_FIXED_UNIVERSE": 1}
    assert result["status"] == "INSUFFICIENT_EVIDENCE" and result["metrics"] is None


def test_late_training_label_is_purged_before_validation() -> None:
    from tests.test_alpha_lab import review
    inputs, pairs, experiment = dataset()
    changed = [review(pair.model_copy(update={"terminal": pair.terminal.model_copy(update={"ingested_at": experiment.validation_start}),
        "benchmark_terminal": pair.benchmark_terminal.model_copy(update={"ingested_at": experiment.validation_start})})) if pair.prediction.decision_timestamp == NOW else pair for pair in pairs]
    report = evaluate_portfolios(inputs, tuple(changed), experiment=experiment)
    assert report["partition_blocks"] == {"TRAIN": 0, "VALIDATION": 1, "TEST": 4}
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["rejected_blocks"] == {"LABEL_NOT_AVAILABLE_BEFORE_PARTITION_BOUNDARY": 1}


def test_configuration_cannot_register_after_observing_training_returns() -> None:
    inputs, pairs, experiment = dataset()
    with pytest.raises(ValueError, match="NOT_PREDECLARED"):
        evaluate_portfolios(inputs, pairs, experiment=experiment.model_copy(update={"registered_at": NOW + timedelta(seconds=1)}))
    with pytest.raises(ValueError, match="DUPLICATE"):
        evaluate_portfolios(inputs, (*pairs, pairs[0]), experiment=experiment)
    bad = experiment.model_dump(mode="json")
    bad["test_start"] = bad["validation_start"]
    with pytest.raises(ValueError, match="TIME_INVALID"):
        PortfolioExperiment.model_validate(bad)


def test_matching_return_cannot_hide_conflicting_benchmark_provenance() -> None:
    from tests.test_alpha_lab import review
    inputs, pairs, experiment = dataset()
    changed = review(pairs[-1].model_copy(update={"benchmark_terminal": pairs[-1].benchmark_terminal.model_copy(update={"source": "CONFLICTING_SOURCE"})}))
    report = evaluate_portfolios(inputs, (*pairs[:-1], changed), experiment=experiment)
    assert report["rejected_blocks"] == {"BENCHMARK_SOURCE_CONFLICT": 1}
    assert report["partition_blocks"] == {"TRAIN": 1, "VALIDATION": 1, "TEST": 3}


def test_decision_time_does_not_override_earlier_information_cutoff() -> None:
    from meridian.lab_evaluation import evaluate_signals
    from tests.test_alpha_lab import review
    inputs, pairs, experiment = dataset()
    changed = tuple(review(pair.model_copy(update={"prediction": pair.prediction.model_copy(update={"information_cutoff": pair.prediction.decision_timestamp - timedelta(seconds=1)})})) for pair in pairs)
    report = evaluate_portfolios(inputs, changed, experiment=experiment)
    assert report["status"] == "INSUFFICIENT_EVIDENCE" and report["metrics"] is None
    assert report["rejected_blocks"] == {"UNREVIEWED_OR_UNALIGNED_EVIDENCE": 6}
    signals = evaluate_signals(inputs, changed, as_of=experiment.evaluation_at, registered_at=experiment.registered_at,
        universe=experiment.universe, universe_available_at=experiment.universe_available_at)
    assert signals["temporal_blocks"] == 0 and signals["metrics"] is None


def test_fresh_process_cli_and_markdown_are_lossless(tmp_path: Path) -> None:
    from meridian.portfolio_lab import PortfolioReplayInput, render_portfolio_report
    inputs, pairs, experiment = dataset()
    replay = PortfolioReplayInput(inputs=inputs, pairs=pairs, experiment=experiment)
    path = tmp_path / "mock-replay.json"
    path.write_text(replay.stable_json(), encoding="utf-8")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    child = subprocess.run([sys.executable, "-m", "meridian.alpha_lab", "portfolio", "--input", str(path)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
    report = evaluate_portfolios(inputs, pairs, experiment=experiment)
    assert json.loads(child.stdout) == report
    markdown = render_portfolio_report(report)
    assert json.loads(markdown.split("```json\n")[1].split("\n```")[0]) == report
    assert {item.name for item in tmp_path.iterdir()} == {"mock-replay.json"}
