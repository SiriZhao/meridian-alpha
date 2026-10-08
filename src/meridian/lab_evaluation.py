"""Purged, paired signal evaluation; deliberately not a portfolio backtest.

Report effective temporal blocks separately from correlated symbol rows.
Research confidence is never interpreted as a probability of an up move.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, localcontext

from meridian.alpha_lab import LabInput, challenger_scores
from meridian.authorization import CertifiedAgentSignal
from meridian.dated_close import ReviewedPricePair, evaluate_close


def _ranks(values: list[Decimal]) -> list[Decimal]:
    """Deterministic average ranks for ties."""
    ordered = sorted(values)
    return [Decimal(ordered.index(value) + 1 + len(ordered) - ordered[::-1].index(value)) / 2 for value in values]


def rank_correlation(scores: list[Decimal], returns: list[Decimal]) -> Decimal | None:
    if len(scores) != len(returns):
        raise ValueError("ALPHA_LAB_RANK_LENGTH_MISMATCH")
    if len(scores) < 3:
        return None
    with localcontext() as context:
        context.prec = 28
        x, y = _ranks(scores), _ranks(returns)
        mx, my = sum(x, Decimal("0")) / len(x), sum(y, Decimal("0")) / len(y)
        covariance = sum(((a - mx) * (b - my) for a, b in zip(x, y, strict=True)), Decimal("0"))
        variance = sum(((a - mx) ** 2 for a in x), Decimal("0")) * sum(((b - my) ** 2 for b in y), Decimal("0"))
        return covariance / variance.sqrt() if variance else None


def evaluate_signals(inputs: tuple[LabInput, ...], pairs: tuple[ReviewedPricePair, ...], *,
                     as_of: datetime, registered_at: datetime, universe: tuple[str, ...],
                     universe_available_at: datetime,
                     research: Mapping[str, CertifiedAgentSignal] | None = None,
                     minimum_temporal_blocks: int = 20) -> dict[str, object]:
    """Evaluate one predeclared fixed universe, with greedy non-overlap purge.

This function does not choose parameters or the universe from outcome returns.
An ex-ante universe attestation is required; it is not historical market-wide
survivorship coverage. Returns include distributions as cash, not reinvestment.
"""
    times = (as_of, registered_at, universe_available_at)
    if any(value.tzinfo is None or value.utcoffset() is None for value in times):
        raise ValueError("ALPHA_LAB_EVALUATION_TIMEZONE_REQUIRED")
    if minimum_temporal_blocks < 2 or not universe or len(set(universe)) != len(universe):
        raise ValueError("ALPHA_LAB_EVALUATION_CONFIGURATION_INVALID")
    data_by_key = {(data.symbol, data.as_of): data for data in inputs}
    if len(data_by_key) != len(inputs) or len({pair.prediction.prediction_id for pair in pairs}) != len(pairs):
        raise ValueError("ALPHA_LAB_EVALUATION_DUPLICATE_INPUT")
    if registered_at > as_of or universe_available_at > registered_at or (pairs and registered_at > min(pair.prediction.decision_timestamp for pair in pairs)):
        raise ValueError("ALPHA_LAB_EXPERIMENT_OR_UNIVERSE_NOT_PREDECLARED")
    if len({(pair.prediction.horizon_days, pair.prediction.benchmark, pair.corporate_action_basis) for pair in pairs}) > 1:
        raise ValueError("ALPHA_LAB_NONCOMPARABLE_HORIZONS_OR_BENCHMARKS")
    rows: list[tuple[datetime, datetime, str, Decimal, Decimal, Decimal, Decimal]] = []
    certified_keys: set[tuple[str, datetime]] = set()
    rejected: dict[str, int] = {}
    for pair in sorted(pairs, key=lambda item: (item.prediction.decision_timestamp, item.prediction.symbol, item.prediction.prediction_id)):
        prediction = pair.prediction
        data = data_by_key.get((prediction.symbol, prediction.decision_timestamp))
        outcome = evaluate_close(pair, as_of=as_of)
        reason = None
        if prediction.symbol not in universe:
            reason = "OUTSIDE_PREDECLARED_UNIVERSE"
        elif data is None or data.evidence_origin != "REVIEWED_RESEARCH":
            reason = "INPUT_NOT_REVIEWED_OR_NOT_ALIGNED"
        elif not outcome.financial_sample_eligible:
            reason = outcome.validation_status.value
        if reason is not None:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        if data is None:
            raise ValueError("ALPHA_LAB_REVIEWED_INPUT_MISSING")
        if outcome.return_at_horizon is None or outcome.benchmark_return is None:
            raise ValueError("ALPHA_LAB_VERIFIED_RETURN_MISSING")
        baseline, enhanced = challenger_scores(data, (research or {}).get(prediction.prediction_id))[1::2]
        if baseline.score is None or enhanced.score is None or baseline.score != prediction.quant_score:
            raise ValueError("ALPHA_LAB_FROZEN_BASELINE_SCORE_MISMATCH")
        if enhanced.certificate_id is not None:
            certified_keys.add((prediction.symbol, prediction.decision_timestamp))
        rows.append((prediction.decision_timestamp, prediction.maturity_at, prediction.symbol,
                     baseline.score, enhanced.score, outcome.return_at_horizon, outcome.benchmark_return))
    groups: dict[tuple[datetime, datetime], list[tuple[datetime, datetime, str, Decimal, Decimal, Decimal, Decimal]]] = {}
    for row in rows:
        groups.setdefault((row[0], row[1]), []).append(row)
    retained = []
    last_maturity: datetime | None = None
    purged = incomplete = 0
    for (decision, maturity), group in sorted(groups.items()):
        if set(row[2] for row in group) != set(universe) or len(group) != len(universe):
            incomplete += len(group)
        elif last_maturity is not None and decision <= last_maturity:
            purged += len(group)
        else:
            retained.append(group)
            last_maturity = maturity
    common = {"schema_version": "meridian-paired-signal-evaluation.v1", "title": "Quant vs Quant+LLM Shadow Evaluation",
              "as_of": as_of.isoformat(), "registered_at": registered_at.isoformat(), "universe": list(universe),
              "eligible_rows": len(rows), "temporal_blocks": len(retained), "required_temporal_blocks": minimum_temporal_blocks,
              "certified_research_rows": sum((row[2], row[0]) in certified_keys for group in retained for row in group),
              "llm_comparison_status": "DESCRIPTIVE_ONLY" if len(retained) >= minimum_temporal_blocks and all((row[2], row[0]) in certified_keys for group in retained for row in group) else "INSUFFICIENT_EVIDENCE",
              "purged_overlapping_rows": purged, "incomplete_universe_rows": incomplete, "rejected": rejected,
              "scope": "PREDECLARED_FIXED_UNIVERSE_SIGNAL_EVALUATION_NOT_PORTFOLIO_PNL",
              "registration_basis": "CALLER_ATTESTED_TIME_NOT_AUTHENTICATED_REGISTRY",
              "portfolio_metrics": "NOT_EVALUABLE", "transaction_costs": "NOT_EVALUABLE_NO_EXECUTION_MODEL",
              "probability_calibration": "NOT_APPLICABLE_CONFIDENCE_IS_NOT_PROBABILITY",
              "uncertainty_intervals": "NOT_ESTIMATED_TEMPORAL_INDEPENDENCE_NOT_PROVEN",
              "automatic_strategy_promotion": "DISABLED", "broker_submission": "DISABLED"}
    if len(retained) < minimum_temporal_blocks:
        return {**common, "status": "INSUFFICIENT_EVIDENCE", "conclusion": "NO_DEMONSTRATED_ALPHA", "metrics": None}
    metrics: dict[str, object] = {}
    with localcontext() as context:
        context.prec = 28
        flat = [row for group in retained for row in group]
        excess = [row[5] - row[6] for row in flat]
        for name, score_index in (("PURE_QUANT", 3), ("QUANT_PLUS_LLM", 4)):
            correlations = [rank_correlation([row[score_index] for row in group], [row[5] - row[6] for row in group]) for group in retained]
            valid = [value for value in correlations if value is not None]
            directional = [row for row in flat if row[score_index] != 0]
            hits = sum((row[score_index] > 0) == (row[5] > 0) for row in directional if row[5] != 0)
            nonzero = sum(row[5] != 0 for row in directional)
            metrics[name] = {"mean_cross_sectional_ic": str(sum(valid) / len(valid)) if valid else None,
                "ic_block_count": len(valid), "directional_count": nonzero,
                "direction_hit_rate": str(Decimal(hits) / nonzero) if nonzero else None}
        metrics["outcome_distribution"] = {"count": len(excess), "mean_excess_return": str(sum(excess) / len(excess)),
                                           "minimum": str(min(excess)), "maximum": str(max(excess))}
    return {**common, "status": "DESCRIPTIVE_SIGNAL_EVALUATION_ONLY", "conclusion": "NO_DEMONSTRATED_ALPHA", "metrics": metrics}
