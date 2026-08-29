"""Deterministic, quant-only research candidate selection."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from meridian.config import ResearchBudgetPolicy
from meridian.schemas import StableModel


class ResearchCandidate(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    quant_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    rank: int = Field(ge=1)
    is_existing_holding: bool
    selection_reasons: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()
    feature_timestamp: datetime | None
    deferred_reason: str | None = None


class ResearchCandidateSet(StableModel):
    as_of: datetime
    candidates: tuple[ResearchCandidate, ...] = ()
    deferred: tuple[ResearchCandidate, ...] = ()
    selection_mode: str
    budget_limit: int = Field(ge=1)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_set(self):
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("candidate set as_of must be timezone-aware")
        all_candidates = self.candidates + self.deferred
        tickers = [candidate.ticker for candidate in all_candidates]
        if len(set(tickers)) != len(tickers):
            raise ValueError("candidate set contains duplicate tickers")
        if len(self.candidates) > self.budget_limit:
            raise ValueError("candidate set exceeds research budget")
        for candidate in all_candidates:
            if candidate.feature_timestamp is not None and candidate.feature_timestamp > self.as_of:
                raise ValueError("candidate feature timestamp is after as_of")
        return self


class CandidateSelector:
    """Select a bounded candidate set from deterministic features only."""

    def build(
        self,
        tickers: list[str] | tuple[str, ...],
        features: Mapping[str, Mapping[str, object]],
        as_of: datetime,
        *,
        existing_holdings: list[str] | tuple[str, ...] = (),
        policy: ResearchBudgetPolicy,
    ) -> ResearchCandidateSet:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("candidate selector as_of must be timezone-aware")
        universe = tuple(sorted({ticker.upper() for ticker in tickers}))
        held = {ticker.upper() for ticker in existing_holdings}
        rows: list[ResearchCandidate] = []
        for ticker in universe:
            context = features.get(ticker, features.get(ticker.upper(), {}))
            if not isinstance(context, Mapping):
                raise ValueError(f"features for {ticker} must be a mapping")
            raw_timestamp = context.get("feature_timestamp")
            timestamp = raw_timestamp if isinstance(raw_timestamp, datetime) else None
            risk_flags = self._strings(context.get("risk_flags", ()))
            if timestamp is None:
                risk_flags = tuple(sorted(set(risk_flags + ("MISSING_FEATURE_TIMESTAMP",))))
            elif timestamp.tzinfo is None or timestamp.utcoffset() is None:
                timestamp = None
                risk_flags = tuple(sorted(set(risk_flags + ("NAIVE_FEATURE_TIMESTAMP",))))
            elif timestamp > as_of:
                raise ValueError(f"feature timestamp is after as_of for {ticker}")
            elif (as_of - timestamp).total_seconds() > policy.max_graph_age_hours * 3600:
                risk_flags = tuple(sorted(set(risk_flags + ("STALE_FEATURE_TIMESTAMP",))))
            score, reasons, missing = self._score(context)
            if missing:
                risk_flags = tuple(sorted(set(risk_flags + ("MISSING_QUANT_FEATURES",))))
                reasons = reasons + ("available quant features are incomplete",)
            is_held = ticker in held
            if is_held:
                reasons = reasons + ("existing holding review",)
            if risk_flags:
                reasons = reasons + ("risk flags present",)
            rows.append(
                ResearchCandidate(
                    ticker=ticker,
                    quant_score=score,
                    rank=1,
                    is_existing_holding=is_held,
                    selection_reasons=tuple(dict.fromkeys(reasons)),
                    risk_flags=risk_flags,
                    feature_timestamp=timestamp,
                )
            )

        required = {
            candidate.ticker
            for candidate in rows
            if candidate.is_existing_holding
            and (
                policy.always_review_existing_holdings
                or policy.existing_holding_review_policy == "always"
                or (
                    policy.existing_holding_review_policy == "if_risk"
                    and candidate.risk_flags
                )
            )
        }
        if len(required) > policy.max_graph_tickers_per_run:
            raise ValueError("research budget cannot review every required holding")

        ordered = sorted(
            rows,
            key=lambda candidate: (
                0 if candidate.ticker in required else 1,
                -candidate.quant_score,
                0 if candidate.risk_flags else 1,
                candidate.ticker,
            ),
        )
        ranked = [candidate.model_copy(update={"rank": index}) for index, candidate in enumerate(ordered, 1)]
        eligible: list[ResearchCandidate] = []
        below_threshold: list[ResearchCandidate] = []
        for candidate in ranked:
            # Missing features are a data-quality warning, not an explicit
            # risk trigger; they must not bypass the minimum-score gate.
            risk_triggered = any(flag != "MISSING_QUANT_FEATURES" for flag in candidate.risk_flags)
            if (
                candidate.ticker not in required
                and not risk_triggered
                and candidate.quant_score < policy.minimum_quant_score
            ):
                below_threshold.append(
                    candidate.model_copy(update={"deferred_reason": "BELOW_MINIMUM_QUANT_SCORE"})
                )
            else:
                eligible.append(candidate)
        valid_eligible = [
            candidate
            for candidate in eligible
            if candidate.feature_timestamp is not None
            and not any(
                flag in candidate.risk_flags
                for flag in ("STALE_FEATURE_TIMESTAMP", "NAIVE_FEATURE_TIMESTAMP")
            )
        ]
        invalid_eligible = [candidate for candidate in eligible if candidate not in valid_eligible]
        selected = tuple(valid_eligible[: policy.max_graph_tickers_per_run])
        selected_tickers = {candidate.ticker for candidate in selected}
        deferred = tuple(
            candidate.model_copy(
                update={"deferred_reason": "BUDGET_LIMIT"}
            )
            for candidate in valid_eligible
            if candidate.ticker not in selected_tickers
        ) + tuple(below_threshold) + tuple(
            candidate.model_copy(
                update={"deferred_reason": "FEATURE_TIMESTAMP_UNAVAILABLE"}
            )
            for candidate in invalid_eligible
            if candidate.ticker not in selected_tickers
        )
        return ResearchCandidateSet(
            as_of=as_of,
            candidates=selected,
            deferred=deferred,
            selection_mode=policy.candidate_selection_mode,
            budget_limit=policy.max_graph_tickers_per_run,
            warnings=(
                f"selected={len(selected)}; deferred={len(deferred)}; "
                f"minimum_quant_score={policy.minimum_quant_score}",
            ),
        )

    @staticmethod
    def _strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("risk_flags must be a sequence")
        return tuple(sorted({str(item) for item in value if str(item).strip()}))

    @staticmethod
    def _score(context: Mapping[str, object]) -> tuple[Decimal, tuple[str, ...], bool]:
        values: list[Decimal] = []
        reasons: list[str] = []
        for name in ("existing_alpha_score", "momentum", "trend"):
            value = context.get(name)
            if value is not None:
                values.append(max(Decimal("-1"), min(Decimal("1"), Decimal(str(value)))))
                reasons.append(f"{name} available")
        volume_ratio = context.get("volume_ratio")
        if volume_ratio is not None:
            values.append(max(Decimal("-1"), min(Decimal("1"), Decimal(str(volume_ratio)) - 1)))
            reasons.append("volume ratio available")
        for name in ("volatility", "drawdown"):
            value = context.get(name)
            if value is not None:
                values.append(max(Decimal("-1"), min(Decimal("1"), -Decimal(str(value)))))
                reasons.append(f"{name} available")
        if not values:
            return Decimal("0"), tuple(reasons), True
        return sum(values, Decimal("0")) / Decimal(len(values)), tuple(reasons), len(values) < 2
