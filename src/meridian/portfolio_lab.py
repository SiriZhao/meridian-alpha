"""Predeclared, purged portfolio experiments with explicit hypothetical costs.

No orders, fills, execution quotes, account state writes or strategy promotion.
Each horizon starts and ends in cash. Unobserved gaps earn an assumed zero cash
return; the benchmark is horizon-rebalanced, never advertised as buy-and-hold.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext

from pydantic import AwareDatetime, Field, model_validator

from meridian.allocation import DeterministicFallbackAllocator
from meridian.alpha_lab import LabInput, challenger_scores
from meridian.authorization import CertifiedAgentSignal
from meridian.config import RiskPolicy
from meridian.dated_close import ReviewedPricePair, evaluate_close
from meridian.risk import RiskEngine
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    AlphaScore,
    FreshnessState,
    StableModel,
)


class PortfolioExperiment(StableModel):
    experiment_id: str = Field(min_length=1)
    registered_at: AwareDatetime
    universe: tuple[str, ...]
    universe_available_at: AwareDatetime
    validation_start: AwareDatetime
    test_start: AwareDatetime
    evaluation_at: AwareDatetime
    risk_policy: RiskPolicy
    commission_bps: Decimal = Field(default=Decimal("1"), ge=0, le=1000, allow_inf_nan=False)
    slippage_bps: tuple[Decimal, ...] = (Decimal("0"), Decimal("5"), Decimal("20"))
    minimum_test_blocks: int = Field(default=20, ge=2)

    @model_validator(mode="after")
    def chronology(self) -> PortfolioExperiment:
        if not self.universe or len(set(self.universe)) != len(self.universe):
            raise ValueError("PORTFOLIO_UNIVERSE_INVALID")
        if not self.universe_available_at <= self.registered_at < self.validation_start < self.test_start < self.evaluation_at:
            raise ValueError("PORTFOLIO_EXPERIMENT_TIME_INVALID")
        if not self.slippage_bps or len(set(self.slippage_bps)) != len(self.slippage_bps) or any(not v.is_finite() or v < 0 or v > 1000 for v in self.slippage_bps):
            raise ValueError("PORTFOLIO_COST_GRID_INVALID")
        return self


class PortfolioReplayInput(StableModel):
    """CLI replay has no deserialization shortcut for certified LLM signals."""
    experiment: PortfolioExperiment
    inputs: tuple[LabInput, ...]
    pairs: tuple[ReviewedPricePair, ...]


def _weights(scores: dict[str, Decimal], at: datetime, policy: RiskPolicy) -> dict[str, Decimal]:
    """Reuse current allocator and risk overlay, with a synthetic unit NAV."""
    account = AccountSnapshot(snapshot_id="isolated-portfolio-unit", account_alias="Schwab-Paper", provider="LAB_ONLY",
        as_of=at, total_equity=Decimal("1"), cash=Decimal("1"), sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED)
    signals = [AlphaScore(ticker=symbol, score=score, confidence=Decimal("1"), expected_direction="BULLISH" if score > 0 else "NEUTRAL",
                          risk_penalty=Decimal("0"), evidence_quality=Decimal("1"), model_source="ISOLATED_LAB") for symbol, score in sorted(scores.items())]
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        target = DeterministicFallbackAllocator().allocate(signals, {}, account, policy)
        approved = RiskEngine().approve(target, account, "NORMAL", policy, sectors=dict.fromkeys(scores, "OPERATIONAL_UNCLASSIFIED")).approved
    return {position.ticker: position.target_weight for position in approved.positions}


def round_trip_return(weights: Mapping[str, Decimal], returns: Mapping[str, Decimal], *, cost_bps: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Self-financing fractional hypothetical exposure; fees charged both ways.

Return, fee fraction and traded-notional fraction are relative to starting NAV.
Cash distributions are included in reviewed terminal wealth. Uniform exit cost
on terminal wealth is a declared conservative approximation, not a fill model.
"""
    values = (*weights.values(), *returns.values(), cost_bps)
    if any(not value.is_finite() for value in values) or cost_bps < 0 or cost_bps > 2000:
        raise ValueError("PORTFOLIO_ARITHMETIC_INPUT_INVALID")
    if set(weights) - set(returns) or any(weight < 0 for weight in weights.values()) or any(value < -1 for value in returns.values()):
        raise ValueError("PORTFOLIO_PRICE_OR_WEIGHT_INVALID")
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        invested = sum(weights.values(), Decimal("0"))
        entry_cost = invested * cost_bps / 10000
        if invested + entry_cost > 1:
            raise ValueError("PORTFOLIO_INSUFFICIENT_CASH_FOR_COSTS")
        terminal = sum((weight * (1 + returns[symbol]) for symbol, weight in weights.items()), Decimal("0"))
        costs = entry_cost + terminal * cost_bps / 10000
        net = terminal - invested - costs
        return net, costs, invested + terminal


def evaluate_portfolios(inputs: tuple[LabInput, ...], pairs: tuple[ReviewedPricePair, ...], *,
                        experiment: PortfolioExperiment,
                        research: Mapping[str, CertifiedAgentSignal] | None = None) -> dict[str, object]:
    """Same reviewed rows, universe, partitions and costs for every challenger.

Parameters are fixed at registration. Training/validation are diagnostics only;
no fitting or model selection is performed. Adjacent endpoint-overlap labels
are purged, as are labels published after the next partition begins.
"""
    index = {(data.symbol, data.as_of): data for data in inputs}
    identities = [(pair.prediction.symbol, pair.prediction.decision_timestamp) for pair in pairs]
    if len(index) != len(inputs) or len(set(identities)) != len(pairs):
        raise ValueError("PORTFOLIO_DUPLICATE_INPUT")
    if pairs and min(pair.prediction.decision_timestamp for pair in pairs) < experiment.registered_at:
        raise ValueError("PORTFOLIO_EXPERIMENT_NOT_PREDECLARED")
    if len({(p.prediction.horizon_days, p.prediction.benchmark, p.corporate_action_basis) for p in pairs}) > 1:
        raise ValueError("PORTFOLIO_NONCOMPARABLE_HORIZONS")
    grouped: dict[tuple[datetime, datetime], list[ReviewedPricePair]] = {}
    for pair in pairs:
        grouped.setdefault((pair.prediction.decision_timestamp, pair.prediction.maturity_at), []).append(pair)
    blocks: dict[str, list[tuple[datetime, dict[str, Decimal], dict[str, dict[str, Decimal]]]]] = {key: [] for key in ("TRAIN", "VALIDATION", "TEST")}
    rejected: dict[str, int] = {}
    last_maturity: datetime | None = None
    certified_test_blocks = 0
    for (at, maturity), group in sorted(grouped.items()):
        partition = "TRAIN" if at < experiment.validation_start else "VALIDATION" if at < experiment.test_start else "TEST"
        boundary = experiment.validation_start if partition == "TRAIN" else experiment.test_start if partition == "VALIDATION" else experiment.evaluation_at
        reason: str | None = None
        if set(pair.prediction.symbol for pair in group) != set(experiment.universe):
            reason = "INCOMPLETE_FIXED_UNIVERSE"
        elif last_maturity is not None and at <= last_maturity:
            reason = "OVERLAPPING_LABEL"
        elif maturity >= boundary or any(pair.reviewed_at is None or pair.reviewed_at >= boundary for pair in group):
            reason = "LABEL_NOT_AVAILABLE_BEFORE_PARTITION_BOUNDARY"
        returns: dict[str, Decimal] = {}
        scores: dict[str, dict[str, Decimal]] = {key: {} for key in ("OPERATIONAL_QUANT", "MULTIFACTOR", "QUANT_PLUS_LLM")}
        benchmark_returns: set[Decimal] = set()
        benchmark_evidence: set[str] = set()
        all_certified = True
        if reason is None:
            for pair in group:
                prediction = pair.prediction
                data = index.get((prediction.symbol, at))
                outcome = evaluate_close(pair, as_of=experiment.evaluation_at)
                if data is None or data.evidence_origin != "REVIEWED_RESEARCH" or data.as_of != prediction.information_cutoff or not outcome.financial_sample_eligible:
                    reason = "UNREVIEWED_OR_UNALIGNED_EVIDENCE"
                    break
                if outcome.return_at_horizon is None or outcome.benchmark_return is None:
                    raise ValueError("PORTFOLIO_VERIFIED_RETURN_MISSING")
                variants = challenger_scores(data, (research or {}).get(prediction.prediction_id))
                if variants[1].score != prediction.quant_score:
                    raise ValueError("PORTFOLIO_FROZEN_BASELINE_MISMATCH")
                if variants[2].score is None:
                    reason = "MULTIFACTOR_HISTORY_INCOMPLETE_COMMON_COHORT"
                    break
                for name, variant in zip(scores, variants[1:], strict=True):
                    if variant.score is None:
                        raise ValueError("PORTFOLIO_SCORE_UNAVAILABLE")
                    scores[name][prediction.symbol] = variant.score
                all_certified = all_certified and variants[3].certificate_id is not None
                returns[prediction.symbol] = outcome.return_at_horizon
                benchmark_returns.add(outcome.benchmark_return)
                benchmark_evidence.add(json.dumps({"inception_price": str(prediction.benchmark_price),
                    "close": pair.benchmark_terminal.model_dump(mode="json"),
                    "actions": [action.model_dump(mode="json") for action in pair.benchmark_actions]}, sort_keys=True))
        if reason is None and (len(benchmark_returns) != 1 or len(benchmark_evidence) != 1):
            reason = "BENCHMARK_SOURCE_CONFLICT"
        if reason is not None:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        returns["__BENCHMARK__"] = next(iter(benchmark_returns))
        try:
            weights = {name: _weights(values, at, experiment.risk_policy) for name, values in scores.items()}
        except DecimalException as error:
            raise ValueError("PORTFOLIO_ALLOCATION_ARITHMETIC_UNREPRESENTABLE") from error
        weights["CASH"] = {}
        # Cash buffer makes benchmark costs self-financing under the same policy.
        weights["HORIZON_BENCHMARK"] = {"__BENCHMARK__": 1 - experiment.risk_policy.min_cash_weight}
        blocks[partition].append((at, returns, weights))
        last_maturity = maturity
        certified_test_blocks += int(partition == "TEST" and all_certified)
    digest = hashlib.sha256(json.dumps({"experiment": experiment.model_dump(mode="json"),
        "inputs": [data.model_dump(mode="json") for data in sorted(inputs, key=lambda item: (item.as_of, item.symbol))],
        "pairs": [pair.model_dump(mode="json") for pair in sorted(pairs, key=lambda item: (item.prediction.decision_timestamp, item.prediction.symbol))],
        "research": {key: value.stable_json() for key, value in sorted((research or {}).items())}}, sort_keys=True).encode()).hexdigest()
    common: dict[str, object] = {"schema_version": "meridian-portfolio-lab.v1", "experiment_digest": digest,
        "experiment": experiment.model_dump(mode="json"), "partition_blocks": {key: len(value) for key, value in blocks.items()},
        "rejected_blocks": rejected, "certified_llm_test_blocks": certified_test_blocks,
        "llm_comparison_status": "DESCRIPTIVE_ONLY" if certified_test_blocks == len(blocks["TEST"]) and certified_test_blocks >= experiment.minimum_test_blocks else "INSUFFICIENT_EVIDENCE",
        "execution_model": "HYPOTHETICAL_FRACTIONAL_HORIZON_ROUND_TRIP_NOT_PAPER_FILLS",
        "cash_return_assumption": "ZERO_DURING_HORIZONS_AND_UNOBSERVED_GAPS",
        "benchmark_basis": "MATCHED_HORIZONS_WITH_CASH_BUFFER_NOT_CONTINUOUS_BUY_AND_HOLD",
        "parameter_selection": "FIXED_EX_ANTE_NO_FITTING_OR_AUTOMATIC_SELECTION",
        "annualized_return": "NOT_ESTIMATED_IRREGULAR_HORIZONS", "intrahorizon_drawdown": "NOT_OBSERVED",
        "uncertainty": "NOT_ESTIMATED_SERIAL_INDEPENDENCE_UNPROVEN", "probability_calibration": "NOT_APPLICABLE",
        "automatic_promotion": "DISABLED", "broker_submission": "DISABLED", "conclusion": "NO_DEMONSTRATED_ALPHA"}
    if len(blocks["TEST"]) < experiment.minimum_test_blocks or not blocks["TRAIN"] or not blocks["VALIDATION"]:
        return {**common, "status": "INSUFFICIENT_EVIDENCE", "metrics": None}
    metrics: dict[str, object] = {}
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        for slippage in sorted(experiment.slippage_bps):
            lane: dict[str, dict[str, object]] = {}
            for name in ("CASH", "HORIZON_BENCHMARK", "OPERATIONAL_QUANT", "MULTIFACTOR", "QUANT_PLUS_LLM"):
                wealth = peak = Decimal("1")
                drawdown = costs = turnover = exposure = Decimal("0")
                concentration = Decimal("0")
                transactions = 0
                period_returns: list[Decimal] = []
                periods: list[dict[str, object]] = []
                try:
                    for at, returns, weights in blocks["TEST"]:
                        net, fee, traded = round_trip_return(weights[name], returns, cost_bps=slippage + experiment.commission_bps)
                        costs += wealth * fee
                        turnover += traded
                        exposure += sum(weights[name].values(), Decimal("0"))
                        concentration += sum((weight * weight for weight in weights[name].values()), Decimal("0"))
                        transactions += 2 * len(weights[name])
                        wealth *= 1 + net
                        peak = max(peak, wealth)
                        drawdown = min(drawdown, wealth / peak - 1)
                        period_returns.append(net)
                        periods.append({"decision_at": at.isoformat(), "target_weights": {symbol: str(weight) for symbol, weight in sorted(weights[name].items())},
                                        "net_return": str(net), "cost_starting_nav_units": str(fee), "traded_notional_starting_nav_units": str(traded)})
                except (ValueError, DecimalException) as error:
                    lane[name] = {"status": "NOT_EVALUABLE", "reason": str(error)}
                    continue
                count = len(period_returns)
                mean = sum(period_returns, Decimal("0")) / count
                volatility = (sum(((v - mean) ** 2 for v in period_returns), Decimal("0")) / count).sqrt()
                lane[name] = {"status": "DESCRIPTIVE_HYPOTHETICAL_ONLY", "cumulative_return": str(wealth - 1),
                    "endpoint_max_drawdown": str(drawdown), "horizon_volatility": str(volatility),
                    "turnover_starting_nav_units": str(turnover), "cost_initial_nav_units": str(costs),
                    "mean_exposure": str(exposure / count), "positive_period_fraction": str(Decimal(sum(v > 0 for v in period_returns)) / count),
                    "mean_absolute_weight_hhi": str(concentration / count), "hypothetical_entry_exit_count": transactions,
                    "period_count": count, "period_returns": [str(v) for v in period_returns], "periods": periods}
            benchmark = lane["HORIZON_BENCHMARK"]
            benchmark_return = benchmark.get("cumulative_return")
            if isinstance(benchmark_return, str):
                for value in lane.values():
                    cumulative = value.get("cumulative_return")
                    if isinstance(cumulative, str):
                        value["excess_cumulative_return_vs_horizon_benchmark"] = str(Decimal(cumulative) - Decimal(benchmark_return))
            metrics[str(slippage)] = lane
    return {**common, "status": "DESCRIPTIVE_PORTFOLIO_EVALUATION_ONLY", "metrics": metrics}


def render_portfolio_report(report: dict[str, object]) -> str:
    """Lossless display projection of one computed result, without re-derivation."""
    return "# Quant vs Quant+LLM Shadow Portfolio Evaluation\n\n" + str(report["status"]) + " / " + str(report["conclusion"]) + "\n\nHypothetical horizon round trips; no production policy changes or broker effects.\n\n```json\n" + json.dumps(report, indent=2, sort_keys=True) + "\n```\n"
