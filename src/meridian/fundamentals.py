"""PIT-safe, bounded certified SEC fundamental fact contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus, StableModel


class CanonicalMetric(StrEnum):
    REVENUE = "REVENUE"
    GROSS_PROFIT = "GROSS_PROFIT"
    OPERATING_INCOME = "OPERATING_INCOME"
    NET_INCOME = "NET_INCOME"
    DILUTED_EPS = "DILUTED_EPS"
    OPERATING_CASH_FLOW = "OPERATING_CASH_FLOW"
    CAPEX = "CAPEX"
    CASH_AND_EQUIVALENTS = "CASH_AND_EQUIVALENTS"
    TOTAL_ASSETS = "TOTAL_ASSETS"
    TOTAL_LIABILITIES = "TOTAL_LIABILITIES"
    SHAREHOLDERS_EQUITY = "SHAREHOLDERS_EQUITY"
    LONG_TERM_DEBT = "LONG_TERM_DEBT"
    SHARES_OUTSTANDING = "SHARES_OUTSTANDING"


class FundamentalContextType(StrEnum):
    INSTANT = "INSTANT"
    QUARTER = "QUARTER"
    YTD = "YTD"
    ANNUAL = "ANNUAL"
    TTM_COMPONENT = "TTM_COMPONENT"


class CanonicalMetricDefinition(StableModel):
    canonical_metric: CanonicalMetric
    taxonomy: str = "us-gaap"
    raw_concepts: tuple[str, ...] = Field(min_length=1)
    expected_units: tuple[str, ...] = Field(min_length=1)
    context_type: FundamentalContextType
    notes: str = ""
    version: str = "v1"
    concept_precedence: tuple[str, ...] = ()
    component_aggregation: str = Field(default="SINGLE", pattern=r"^(SINGLE|SUM_COMPONENTS)$")


_DEFINITIONS = (
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.REVENUE, raw_concepts=("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"), expected_units=("USD",), context_type=FundamentalContextType.QUARTER, notes="Top-line revenue; quarter/YTD/annual contexts are kept distinct.", concept_precedence=("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.GROSS_PROFIT, raw_concepts=("GrossProfit",), expected_units=("USD",), context_type=FundamentalContextType.QUARTER),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.OPERATING_INCOME, raw_concepts=("OperatingIncomeLoss",), expected_units=("USD",), context_type=FundamentalContextType.QUARTER),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.NET_INCOME, raw_concepts=("NetIncomeLoss",), expected_units=("USD",), context_type=FundamentalContextType.QUARTER),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.DILUTED_EPS, raw_concepts=("EarningsPerShareDiluted",), expected_units=("USD/shares",), context_type=FundamentalContextType.QUARTER),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.OPERATING_CASH_FLOW, raw_concepts=("NetCashProvidedByUsedInOperatingActivities",), expected_units=("USD",), context_type=FundamentalContextType.QUARTER),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.CAPEX, raw_concepts=("PaymentsToAcquirePropertyPlantAndEquipment",), expected_units=("USD",), context_type=FundamentalContextType.QUARTER),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.CASH_AND_EQUIVALENTS, raw_concepts=("CashAndCashEquivalentsAtCarryingValue",), expected_units=("USD",), context_type=FundamentalContextType.INSTANT),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.TOTAL_ASSETS, raw_concepts=("Assets",), expected_units=("USD",), context_type=FundamentalContextType.INSTANT),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.TOTAL_LIABILITIES, raw_concepts=("Liabilities",), expected_units=("USD",), context_type=FundamentalContextType.INSTANT),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.SHAREHOLDERS_EQUITY, raw_concepts=("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"), expected_units=("USD",), context_type=FundamentalContextType.INSTANT, concept_precedence=("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.LONG_TERM_DEBT, raw_concepts=("LongTermDebtCurrent", "LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"), expected_units=("USD",), context_type=FundamentalContextType.INSTANT, notes="Use a reported total when present; otherwise sum current and non-current components for the same filing/context.", concept_precedence=("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtCurrent", "LongTermDebtNoncurrent"), component_aggregation="SUM_COMPONENTS"),
    CanonicalMetricDefinition(canonical_metric=CanonicalMetric.SHARES_OUTSTANDING, raw_concepts=("EntityCommonStockSharesOutstanding", "CommonStocksIncludingAdditionalPaidInCapitalMember"), expected_units=("shares",), context_type=FundamentalContextType.INSTANT, concept_precedence=("EntityCommonStockSharesOutstanding",)),
)

CANONICAL_METRIC_REGISTRY: Mapping[tuple[str, str], CanonicalMetricDefinition] = {
    (definition.taxonomy, concept): definition
    for definition in _DEFINITIONS
    for concept in definition.raw_concepts
}

# Backward-compatible simple mapping used by the earlier contract.
CONCEPT_REGISTRY: Mapping[str, CanonicalMetric] = {
    concept: definition.canonical_metric
    for (_, concept), definition in CANONICAL_METRIC_REGISTRY.items()
}


def canonical_definition(taxonomy: str, concept: str) -> CanonicalMetricDefinition | None:
    return CANONICAL_METRIC_REGISTRY.get((taxonomy, concept))


_ACCESSION = re.compile(r"^(\d{10})-\d{2}-\d{6}$")


def _as_utc_midnight(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("SEC period datetime must be timezone-aware")
        return value.astimezone(UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


class SECNumericObservation(StableModel):
    """Uncertified raw Company Facts observation; no sentiment is attached."""

    observation_id: str = Field(min_length=1, max_length=160)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    cik: str = Field(pattern=r"^\d{10}$")
    taxonomy: str = Field(min_length=1, max_length=64)
    concept: str = Field(min_length=1, max_length=256)
    raw_concept: str | None = None
    value: Decimal
    unit: str = Field(min_length=1, max_length=64)
    period_start: date | None = None
    period_end: date
    frame: str | None = Field(default=None, max_length=64)
    context_id: str | None = Field(default=None, max_length=256)
    fiscal_year: int | None = None
    fiscal_period: str | None = Field(default=None, max_length=16)
    form: str = Field(min_length=1, max_length=32)
    filed_at: date
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    source_uri: str = Field(min_length=1, max_length=2000)
    retrieved_at: datetime
    source_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_observation(self) -> SECNumericObservation:
        if self.raw_concept is None:
            object.__setattr__(self, "raw_concept", self.concept)
        if self.period_start is not None and self.period_start >= self.period_end:
            raise ValueError("SEC period_start must precede period_end")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("SEC retrieved_at must be timezone-aware")
        if not self.value.is_finite():
            raise ValueError("SEC numeric value must be finite")
        return self


class CertifiedFundamentalFact(StableModel):
    fact_id: str
    ticker: str
    cik: str
    accession_number: str
    accession_issuer_cik: str | None = None
    form: str
    taxonomy: str
    concept: str
    raw_concept: str | None = None
    canonical_metric: CanonicalMetric | None = None
    value: Decimal
    unit: str
    period_start: datetime | None = None
    period_end: datetime
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    frame: str | None = None
    context_id: str | None = None
    context_type: FundamentalContextType | None = None
    filed_at: datetime | None = None
    accepted_at: datetime
    available_at: datetime
    retrieved_at: datetime
    source_uri: str
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: str
    point_in_time_status: EvidencePointInTimeStatus
    supersedes_fact_id: str | None = None

    @model_validator(mode="after")
    def pit(self) -> CertifiedFundamentalFact:
        if (
            self.accepted_at != self.available_at
            or self.point_in_time_status is not EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
        ):
            raise ValueError("fundamental fact requires exact certified SEC acceptance time")
        if self.period_start and self.period_start >= self.period_end:
            raise ValueError("invalid duration context")
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() is None:
            raise ValueError("accepted_at must be timezone-aware")
        if _ACCESSION.fullmatch(self.accession_number) is None:
            raise ValueError("invalid SEC accession number")
        if self.accession_issuer_cik is not None and self.accession_issuer_cik != self.cik:
            raise ValueError("CIK_ACCESSION_MISMATCH")
        if self.raw_concept is None:
            object.__setattr__(self, "raw_concept", self.concept)
        if not self.value.is_finite():
            raise ValueError("fundamental value must be finite")
        return self


def classify_context(
    *, period_start: date | datetime | None, period_end: date | datetime,
    form: str = "", fiscal_period: str | None = None,
) -> FundamentalContextType:
    if period_start is None:
        return FundamentalContextType.INSTANT
    start = period_start.date() if isinstance(period_start, datetime) else period_start
    end = period_end.date() if isinstance(period_end, datetime) else period_end
    days = (end - start).days + 1
    fp = (fiscal_period or "").upper()
    if fp == "FY" or (form.upper() in {"10-K", "10-K/A"} and days >= 300):
        return FundamentalContextType.ANNUAL
    if days <= 120:
        return FundamentalContextType.QUARTER
    if days <= 300:
        return FundamentalContextType.YTD
    return FundamentalContextType.ANNUAL


def _periods_compatible(left: CertifiedFundamentalFact, right: CertifiedFundamentalFact) -> bool:
    """Check period/unit compatibility for formulas across different metrics."""
    if left.unit != right.unit:
        return False
    left_context = _fact_context(left)
    right_context = _fact_context(right)
    if left_context is not right_context:
        return False
    if left_context is FundamentalContextType.INSTANT:
        return left.period_start is None and right.period_start is None
    if left.period_start != right.period_start or left.period_end != right.period_end:
        return False
    if left.fiscal_period and right.fiscal_period:
        return left.fiscal_period.upper() == right.fiscal_period.upper()
    return True


class ComparableFundamentalSeries(StableModel):
    metric: CanonicalMetric
    context_type: FundamentalContextType
    current_fact_id: str
    prior_fact_id: str
    current_period_end: datetime
    prior_period_end: datetime
    current_value: Decimal
    prior_value: Decimal
    unit: str
    yoy_change: Decimal | None = None
    cutoff: datetime
    input_fact_ids: tuple[str, str]
    content_hash: str
    available_at: datetime | None = None

    @property
    def comparison_available_at(self) -> datetime | None:
        return self.available_at


class DerivedFundamentalMetric(StableModel):
    metric: str
    value: Decimal
    input_fact_ids: tuple[str, ...]
    formula: str
    cutoff: datetime
    derived_at: datetime
    period_start: datetime | None = None
    period_end: datetime | None = None
    derivation_version: str = "v2"
    content_hash: str
    available_at: datetime | None = None

    @property
    def derived_available_at(self) -> datetime | None:
        return self.available_at


class CertifiedFundamentalSnapshot(StableModel):
    ticker: str
    decision_as_of: datetime
    latest_accession: str | None = None
    latest_form: str | None = None
    latest_accepted_at: datetime | None = None
    latest_source_uri: str | None = None
    facts: tuple[CertifiedFundamentalFact, ...] = ()
    comparable_facts: tuple[CertifiedFundamentalFact, ...] = ()
    comparable_series: tuple[ComparableFundamentalSeries, ...] = ()
    derived: tuple[DerivedFundamentalMetric, ...] = ()
    missing_metrics: tuple[str, ...] = ()
    ambiguous_metrics: tuple[str, ...] = ()
    non_comparable_metrics: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    restatement_status: str = "NO_RESTATEMENT_DETECTED"
    source_hashes: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


def _fact_context(fact: CertifiedFundamentalFact) -> FundamentalContextType:
    return fact.context_type or classify_context(
        period_start=fact.period_start,
        period_end=fact.period_end,
        form=fact.form,
        fiscal_period=fact.fiscal_period,
    )


def contexts_compatible(left: CertifiedFundamentalFact, right: CertifiedFundamentalFact) -> bool:
    """Require same metric/unit/context; quarter and YTD never mix."""
    if left.canonical_metric != right.canonical_metric or left.unit != right.unit:
        return False
    left_context = _fact_context(left)
    right_context = _fact_context(right)
    if left_context is not right_context:
        return False
    if left_context is FundamentalContextType.INSTANT:
        return left.period_start is None and right.period_start is None
    if left.fiscal_period and right.fiscal_period:
        return left.fiscal_period.upper() == right.fiscal_period.upper()
    return True


def _comparable_prior(
    current: CertifiedFundamentalFact, candidates: Sequence[CertifiedFundamentalFact]
) -> CertifiedFundamentalFact | None:
    eligible = [
        item for item in candidates
        if item.period_end < current.period_end and contexts_compatible(current, item)
    ]
    if not eligible:
        return None
    target = current.period_end - timedelta(days=365)
    return min(
        eligible,
        key=lambda item: (
            abs((item.period_end - target).total_seconds()),
            -item.available_at.timestamp(),
            item.fact_id,
        ),
    )


def _derived(
    metric: str,
    value: Decimal,
    ids: tuple[str, ...],
    formula: str,
    cutoff: datetime,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    available_at: datetime | None = None,
) -> DerivedFundamentalMetric:
    raw = f"{metric}|{value}|{ids}|{formula}|{cutoff.isoformat()}|{period_start}|{period_end}|{available_at}|v2"
    return DerivedFundamentalMetric(
        metric=metric,
        value=value,
        input_fact_ids=ids,
        formula=formula,
        cutoff=cutoff,
        derived_at=cutoff,
        period_start=period_start,
        period_end=period_end,
        available_at=available_at,
        content_hash=hashlib.sha256(raw.encode()).hexdigest(),
    )


def build_snapshot(
    ticker: str, facts: tuple[CertifiedFundamentalFact, ...], cutoff: datetime
) -> CertifiedFundamentalSnapshot:
    """Select only known-at-cutoff facts and derive comparable fundamentals."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("fundamental cutoff must be timezone-aware")
    normalized_ticker = ticker.upper()
    eligible = tuple(
        fact
        for fact in facts
        if fact.ticker == normalized_ticker
        and fact.available_at <= cutoff
        and fact.point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
    )
    by_metric: dict[CanonicalMetric, list[CertifiedFundamentalFact]] = {}
    excluded: list[str] = []
    for fact in eligible:
        if fact.canonical_metric is None:
            excluded.append(f"{fact.fact_id}:UNKNOWN_CANONICAL_MAPPING")
            continue
        definition = canonical_definition(fact.taxonomy, fact.raw_concept or fact.concept)
        if definition is not None and fact.unit not in definition.expected_units:
            excluded.append(f"{fact.fact_id}:UNIT_MISMATCH:{fact.unit}")
            continue
        by_metric.setdefault(fact.canonical_metric, []).append(fact)

    selected: dict[CanonicalMetric, CertifiedFundamentalFact] = {}
    ambiguous: list[str] = []
    non_comparable: list[str] = []
    instant_metrics = {
        CanonicalMetric.CASH_AND_EQUIVALENTS,
        CanonicalMetric.TOTAL_ASSETS,
        CanonicalMetric.TOTAL_LIABILITIES,
        CanonicalMetric.SHAREHOLDERS_EQUITY,
        CanonicalMetric.LONG_TERM_DEBT,
    }
    context_rank = {
        FundamentalContextType.INSTANT: 4,
        FundamentalContextType.QUARTER: 3,
        FundamentalContextType.ANNUAL: 2,
        FundamentalContextType.YTD: 1,
        FundamentalContextType.TTM_COMPONENT: 0,
    }
    for metric, values in by_metric.items():
        candidates = sorted(
            values,
            key=lambda item: (item.period_end, item.available_at, item.accession_number, item.fact_id),
            reverse=True,
        )
        if metric not in instant_metrics:
            candidates = sorted(
                candidates,
                key=lambda item: (item.period_end, context_rank[_fact_context(item)], item.available_at),
                reverse=True,
            )
        definition = next(
            (canonical_definition(item.taxonomy, item.raw_concept or item.concept) for item in candidates
             if canonical_definition(item.taxonomy, item.raw_concept or item.concept) is not None),
            None,
        )
        # For balance-sheet debt, current and non-current components are
        # additive when they describe the same instant.  A reported combined
        # concept remains preferred and is never summed with its components.
        if definition is not None and definition.component_aggregation == "SUM_COMPONENTS":
            top_period = candidates[0].period_end
            top_context = _fact_context(candidates[0])
            same_context = [item for item in candidates if item.period_end == top_period and _fact_context(item) is top_context]
            component_names = {item.raw_concept or item.concept for item in same_context}
            has_reported_total = any("AndFinanceLeaseObligations" in name and not name.endswith(("Current", "Noncurrent")) for name in component_names)
            debt_components = [item for item in same_context if (item.raw_concept or item.concept).endswith(("Current", "Noncurrent"))]
            if len(debt_components) >= 2 and not has_reported_total and sum(1 for item in debt_components if item.period_start is None) == len(debt_components):
                seed = debt_components[0]
                value = sum((item.value for item in debt_components), Decimal("0"))
                digest = hashlib.sha256("|".join(sorted(item.fact_id for item in debt_components)).encode()).hexdigest()
                selected[metric] = seed.model_copy(update={
                    "fact_id": f"{seed.ticker.lower()}_{metric.value.lower()}_components_{digest[:16]}",
                    "concept": "LongTermDebtComponents",
                    "raw_concept": "LongTermDebtComponents",
                    "value": value,
                    "source_hash": digest,
                })
                for duplicate in candidates:
                    if duplicate.fact_id not in {item.fact_id for item in debt_components}:
                        non_comparable.append(f"{duplicate.fact_id}:NON_COMPARABLE_CONTEXT")
                continue
        if definition is not None and definition.concept_precedence:
            precedence = {name: index for index, name in enumerate(definition.concept_precedence)}
            candidates = sorted(candidates, key=lambda item: precedence.get(item.raw_concept or item.concept, len(precedence)))
        selected[metric] = candidates[0]
        top = selected[metric]
        top_concept = top.raw_concept or top.concept
        for duplicate in candidates[1:]:
            duplicate_concept = duplicate.raw_concept or duplicate.concept
            if duplicate.period_end == top.period_end and _fact_context(duplicate) is not _fact_context(top):
                ambiguous.append(f"{metric.value}:MULTIPLE_CONTEXTS:{duplicate.fact_id}")
            elif duplicate.period_end == top.period_end and _fact_context(duplicate) is _fact_context(top) and duplicate_concept != top_concept:
                # Distinct concepts for one canonical value are only accepted
                # when the registry's explicit precedence resolves them. If
                # they tie or no registry exists, keep the metric out.
                if definition is None or not definition.concept_precedence:
                    ambiguous.append(f"{metric.value}:AMBIGUOUS_CANONICAL_MAPPING")
            elif duplicate.unit != selected[metric].unit or not contexts_compatible(duplicate, selected[metric]):
                non_comparable.append(f"{duplicate.fact_id}:NON_COMPARABLE_CONTEXT")
        if any(flag.startswith(f"{metric.value}:AMBIGUOUS_CANONICAL_MAPPING") for flag in ambiguous):
            # Do not expose a guessed current fact when the registry cannot
            # resolve a same-period concept collision.
            selected.pop(metric, None)

    selected_values = tuple(selected.values())
    comparable: list[CertifiedFundamentalFact] = []
    series: list[ComparableFundamentalSeries] = []
    for metric, current in selected.items():
        prior = _comparable_prior(current, by_metric.get(metric, ()))
        if prior is None:
            continue
        if prior.fact_id not in {item.fact_id for item in comparable}:
            comparable.append(prior)
        yoy = None if prior.value == 0 else (current.value - prior.value) / abs(prior.value)
        raw = f"{metric.value}|{current.fact_id}|{prior.fact_id}|{cutoff.isoformat()}|{yoy}"
        series.append(
            ComparableFundamentalSeries(
                metric=metric,
                context_type=_fact_context(current),
                current_fact_id=current.fact_id,
                prior_fact_id=prior.fact_id,
                current_period_end=current.period_end,
                prior_period_end=prior.period_end,
                current_value=current.value,
                prior_value=prior.value,
                unit=current.unit,
                yoy_change=yoy,
                cutoff=cutoff,
                input_fact_ids=(current.fact_id, prior.fact_id),
                content_hash=hashlib.sha256(raw.encode()).hexdigest(),
                available_at=max(current.available_at, prior.available_at),
            )
        )

    derived: list[DerivedFundamentalMetric] = []
    for item in series:
        if item.yoy_change is not None:
            derived.append(
                _derived(
                    f"{item.metric.value}_YOY",
                    item.yoy_change,
                    item.input_fact_ids,
                    f"({item.current_fact_id} - {item.prior_fact_id}) / abs({item.prior_fact_id})",
                    cutoff,
                    period_end=item.current_period_end,
                    available_at=item.available_at,
                )
            )

    def get_current(metric: CanonicalMetric) -> CertifiedFundamentalFact | None:
        return selected.get(metric)

    revenue = get_current(CanonicalMetric.REVENUE)
    gross = get_current(CanonicalMetric.GROSS_PROFIT)
    operating = get_current(CanonicalMetric.OPERATING_INCOME)
    net = get_current(CanonicalMetric.NET_INCOME)
    ocf = get_current(CanonicalMetric.OPERATING_CASH_FLOW)
    capex = get_current(CanonicalMetric.CAPEX)
    if revenue and revenue.value != 0:
        for fact, name in (
            (gross, "GROSS_MARGIN"),
            (operating, "OPERATING_MARGIN"),
            (net, "NET_MARGIN"),
            (ocf, "OCF_MARGIN"),
        ):
            if fact and _periods_compatible(fact, revenue):
                derived.append(
                    _derived(
                        name,
                        fact.value / revenue.value,
                        (fact.fact_id, revenue.fact_id),
                        f"{fact.fact_id} / {revenue.fact_id}",
                        cutoff,
                        period_end=fact.period_end,
                        available_at=max(fact.available_at, revenue.available_at),
                    )
                )
    if ocf and capex and _periods_compatible(ocf, capex):
        fcf = ocf.value - capex.value
        derived.append(
            _derived(
                "FREE_CASH_FLOW",
                fcf,
                (ocf.fact_id, capex.fact_id),
                "OPERATING_CASH_FLOW - CAPEX",
                cutoff,
                period_start=ocf.period_start,
                period_end=ocf.period_end,
                available_at=max(ocf.available_at, capex.available_at),
            )
        )
        if revenue and revenue.value != 0 and _periods_compatible(ocf, revenue):
            derived.append(
                _derived(
                    "FCF_MARGIN",
                    fcf / revenue.value,
                    (ocf.fact_id, capex.fact_id, revenue.fact_id),
                    "(OPERATING_CASH_FLOW - CAPEX) / REVENUE",
                    cutoff,
                    period_end=ocf.period_end,
                    available_at=max(ocf.available_at, capex.available_at, revenue.available_at),
                )
            )

    latest = max(selected_values, key=lambda item: (item.available_at, item.period_end), default=None)
    missing = tuple(metric.value for metric in CanonicalMetric if metric not in selected)
    flags = tuple(sorted(set(excluded + ambiguous + non_comparable)))
    return CertifiedFundamentalSnapshot(
        ticker=normalized_ticker,
        decision_as_of=cutoff,
        latest_accession=latest.accession_number if latest else None,
        latest_form=latest.form if latest else None,
        latest_accepted_at=latest.accepted_at if latest else None,
        latest_source_uri=latest.source_uri if latest else None,
        facts=tuple(sorted(selected_values, key=lambda item: item.canonical_metric.value if item.canonical_metric else "")),
        comparable_facts=tuple(sorted(comparable, key=lambda item: item.fact_id)),
        comparable_series=tuple(sorted(series, key=lambda item: item.metric.value)),
        derived=tuple(sorted(derived, key=lambda item: item.metric)),
        missing_metrics=missing,
        ambiguous_metrics=tuple(sorted(set(ambiguous))),
        non_comparable_metrics=tuple(sorted(set(non_comparable))),
        quality_flags=flags,
        restatement_status="PIT_VERSIONED_BY_ACCESSION",
        source_hashes=tuple(sorted({item.source_hash for item in (*selected_values, *comparable)})),
        excluded=tuple(excluded),
    )


def snapshot_to_evidence_items(snapshot: CertifiedFundamentalSnapshot) -> tuple[EvidenceItem, ...]:
    """Create three bounded certified evidence bundles for a grounding view."""
    if not snapshot.facts:
        return ()
    current_payload = [
        {
            "fact_id": fact.fact_id,
            "metric": fact.canonical_metric.value if fact.canonical_metric else None,
            "raw_concept": fact.raw_concept,
            "value": str(fact.value),
            "unit": fact.unit,
            "context_type": _fact_context(fact).value,
            "period_start": fact.period_start.isoformat() if fact.period_start else None,
            "period_end": fact.period_end.isoformat(),
            "accession_number": fact.accession_number,
            "accepted_at": fact.accepted_at.isoformat(),
        }
        for fact in snapshot.facts
    ]
    comparison_payload = [
        {
            "metric": item.metric.value,
            "context_type": item.context_type.value,
            "current_fact_id": item.current_fact_id,
            "prior_fact_id": item.prior_fact_id,
            "current_value": str(item.current_value),
            "prior_value": str(item.prior_value),
            "yoy_change": str(item.yoy_change) if item.yoy_change is not None else None,
            "unit": item.unit,
            "cutoff": item.cutoff.isoformat(),
            "content_hash": item.content_hash,
        }
        for item in snapshot.comparable_series
    ]
    derived_payload = [
        {
            "metric": item.metric,
            "value": str(item.value),
            "formula": item.formula,
            "input_fact_ids": list(item.input_fact_ids),
            "period_end": item.period_end.isoformat() if item.period_end else None,
            "cutoff": item.cutoff.isoformat(),
            "content_hash": item.content_hash,
        }
        for item in snapshot.derived
    ]
    base = {
        "ticker": snapshot.ticker,
        "latest_accession": snapshot.latest_accession,
        "latest_accepted_at": snapshot.latest_accepted_at.isoformat() if snapshot.latest_accepted_at else None,
        "facts": current_payload,
        "comparisons": comparison_payload,
        "derived": derived_payload,
        "quality_flags": list(snapshot.quality_flags),
    }
    encoded = json.dumps(base, sort_keys=True, separators=(",", ":"))
    observed_at = snapshot.latest_accepted_at or snapshot.decision_as_of
    availability_inputs = [fact.available_at for fact in snapshot.facts]
    availability_inputs.extend(fact.available_at for fact in snapshot.comparable_facts)
    availability_inputs.extend(item.available_at for item in snapshot.comparable_series if item.available_at is not None)
    availability_inputs.extend(item.available_at for item in snapshot.derived if item.available_at is not None)
    bundle_available_at = max(availability_inputs, default=snapshot.decision_as_of)
    common = dict(
        ticker=snapshot.ticker,
        provider="sec-edgar-accession-certified",
        source="SEC:EDGAR_ACCEPTANCE_METADATA",
        observed_at=observed_at,
        available_at=bundle_available_at,
        retrieved_at=snapshot.decision_as_of,
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )
    bundles = (
        ("latest", "Certified SEC latest filing facts", {"facts": current_payload, "latest_accession": snapshot.latest_accession, "accepted_at": base["latest_accepted_at"]}),
        ("comparables", "Certified SEC comparable periods", {"comparisons": comparison_payload}),
        ("derived", "Certified SEC derived fundamentals", {"derived": derived_payload, "quality_flags": list(snapshot.quality_flags[:20])}),
    )
    items: list[EvidenceItem] = []
    for kind, title, payload in bundles:
        summary = f"{snapshot.ticker} {kind} bundle; all values link to exact SEC accessions and acceptance timestamps."
        digest = hashlib.sha256(f"{snapshot.ticker}|{kind}|{encoded}".encode()).hexdigest()
        items.append(
            EvidenceItem(
                **common,
                evidence_id=f"{snapshot.ticker.lower()}_fundamental_{kind}",
                title=title,
                document_id=snapshot.latest_accession,
                uri=snapshot.latest_source_uri,
                content_hash=digest,
                evidence_type="certified_fundamental",
                summary=summary,
                structured_payload=payload,
            )
        )
    return tuple(items)



class SECTickerResolver:
    """Resolve one unambiguous SEC ticker from the official company-tickers feed."""
    source_uri = "https://www.sec.gov/files/company_tickers.json"

    def __init__(self, *, opener: Callable[..., Any] = urlopen, clock: Callable[[], datetime] | None = None) -> None:
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))
        self._cache: dict[str, tuple[str, str, str | None, datetime]] = {}

    def resolve(self, ticker: str) -> tuple[str, str, str | None, datetime]:
        key = ticker.strip().upper()
        if key in self._cache:
            return self._cache[key]
        retrieved = self.clock()
        raw = self.opener(Request(self.source_uri, headers={"User-Agent": "MeridianAlpha research contact unavailable"}), timeout=10).read()
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
        rows = payload.values() if isinstance(payload, Mapping) else ()
        matches = [row for row in rows if isinstance(row, Mapping) and str(row.get("ticker", "")).upper() == key]
        if len(matches) != 1:
            raise ValueError("SEC_TICKER_AMBIGUOUS_OR_UNAVAILABLE")
        row = matches[0]
        cik = str(row.get("cik_str", "")).zfill(10)
        name = str(row.get("title", ""))
        if not cik.isdigit() or not name:
            raise ValueError("SEC_TICKER_RESOLUTION_MALFORMED")
        result = (cik, name, None, retrieved)
        self._cache[key] = result
        return result

class SECCompanyFactsNumericProvider:
    """Dedicated raw numeric SEC Company Facts lane.

    This adapter stops at structured observations. It creates certified facts
    only after each observation joins exact SEC submissions metadata with an
    acceptance timestamp.
    """

    provider_name = "sec-edgar-companyfacts-numeric"
    network_capable = True
    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
        user_agent: str = "MeridianAlpha research contact unavailable",
        resolver: Any | None = None,
    ) -> None:
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))
        self.user_agent = user_agent
        self.resolver = resolver or SECTickerResolver(opener=opener, clock=self.clock)
        self.last_exclusions: tuple[str, ...] = ()
        self.last_identity: tuple[str, str, str | None, datetime] | None = None

    def get_observations(self, ticker: str) -> tuple[SECNumericObservation, ...]:
        normalized_ticker = ticker.upper()
        try:
            identity = self.resolver.resolve(normalized_ticker)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("SEC_CIK_UNAVAILABLE") from error
        self.last_identity = identity
        cik = identity[0]
        retrieved_at = self.clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("SEC clock must be timezone-aware")
        source_uri = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        response = self.opener(
            Request(source_uri, headers={"User-Agent": self.user_agent}), timeout=10
        )
        raw = response.read()
        payload = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("SEC_COMPANYFACTS_MALFORMED") from error
        if not isinstance(data, Mapping):
            raise ValueError("SEC_COMPANYFACTS_MALFORMED")
        reported_cik = data.get("cik")
        if reported_cik is not None and str(reported_cik).zfill(10) != cik:
            raise ValueError("SEC_CIK_MISMATCH")
        facts = data.get("facts", {})
        if not isinstance(facts, Mapping):
            raise ValueError("SEC_COMPANYFACTS_MALFORMED")
        source_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        observations: list[SECNumericObservation] = []
        for taxonomy, concepts in facts.items():
            if not isinstance(taxonomy, str) or not isinstance(concepts, Mapping):
                continue
            for concept, definition in concepts.items():
                if not isinstance(concept, str) or not isinstance(definition, Mapping):
                    continue
                units = definition.get("units", {})
                if not isinstance(units, Mapping):
                    continue
                for unit, rows in units.items():
                    if not isinstance(unit, str) or not isinstance(rows, list):
                        continue
                    for row in rows:
                        if not isinstance(row, Mapping):
                            continue
                        accession = row.get("accn")
                        form = row.get("form")
                        end = row.get("end")
                        filed = row.get("filed")
                        value = row.get("val")
                        if not all(isinstance(item, str) and item for item in (accession, form, end, filed)):
                            continue
                        if value is None:
                            continue
                        try:
                            period_end = date.fromisoformat(str(end))
                            period_start = (
                                date.fromisoformat(str(row["start"]))
                                if isinstance(row.get("start"), str)
                                else None
                            )
                            filed_at = date.fromisoformat(str(filed))
                            numeric_value = Decimal(str(value))
                        except (ValueError, ArithmeticError):
                            continue
                        if not _ACCESSION.fullmatch(str(accession)):
                            continue
                        context = str(row.get("ctx", "")) or None
                        observation_id = hashlib.sha256(
                            f"{normalized_ticker}|{taxonomy}|{concept}|{unit}|{accession}|{period_start}|{period_end}|{value}|{context}".encode()
                        ).hexdigest()[:32]
                        try:
                            observations.append(
                                SECNumericObservation(
                                    observation_id=observation_id,
                                    ticker=normalized_ticker,
                                    cik=cik,
                                    taxonomy=taxonomy,
                                    concept=concept,
                                    raw_concept=concept,
                                    value=numeric_value,
                                    unit=unit,
                                    period_start=period_start,
                                    period_end=period_end,
                                    frame=str(row.get("frame")) if row.get("frame") else None,
                                    context_id=context,
                                    fiscal_year=int(row["fy"]) if row.get("fy") is not None else None,
                                    fiscal_period=str(row.get("fp")) if row.get("fp") else None,
                                    form=str(form),
                                    filed_at=filed_at,
                                    accession_number=str(accession),
                                    source_uri=source_uri,
                                    retrieved_at=retrieved_at,
                                    source_hash=source_hash,
                                )
                            )
                        except (ValueError, ArithmeticError, TypeError):
                            continue
        return tuple(sorted(observations, key=lambda item: item.observation_id))

    def certify_observations(
        self,
        observations: Sequence[SECNumericObservation],
        *,
        metadata_provider: Any,
        decision_as_of: datetime,
    ) -> tuple[CertifiedFundamentalFact, ...]:
        """Join raw observations to exact SEC acceptance metadata, fail closed."""
        if decision_as_of.tzinfo is None or decision_as_of.utcoffset() is None:
            raise ValueError("decision_as_of must be timezone-aware")
        metadata_cache: dict[str, Any | None] = {}
        certified: list[CertifiedFundamentalFact] = []
        exclusions: list[str] = []
        for observation in observations:
            accession = observation.accession_number
            if accession not in metadata_cache:
                try:
                    metadata_cache[accession] = metadata_provider.get_metadata(
                        observation.cik, accession
                    )
                except Exception as error:  # noqa: BLE001 - provider boundary
                    metadata_cache[accession] = None
                    exclusions.append(f"{observation.observation_id}:METADATA_ERROR:{type(error).__name__}")
            metadata = metadata_cache[accession]
            if metadata is None:
                exclusions.append(f"{observation.observation_id}:UNVERIFIED_MISSING_ACCESSION_METADATA")
                continue
            if str(getattr(metadata, "cik", "")).zfill(10) != observation.cik:
                exclusions.append(f"{observation.observation_id}:CIK_MISMATCH")
                continue
            if str(getattr(metadata, "accession_number", "")) != accession:
                exclusions.append(f"{observation.observation_id}:ACCESSION_MISMATCH")
                continue
            accession_issuer_cik = getattr(metadata, "accession_issuer_cik", None)
            if accession_issuer_cik is not None and str(accession_issuer_cik).zfill(10) != observation.cik:
                exclusions.append(f"{observation.observation_id}:CIK_ACCESSION_MISMATCH")
                continue
            accepted_at = getattr(metadata, "acceptance_datetime", None)
            if not isinstance(accepted_at, datetime) or accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
                exclusions.append(f"{observation.observation_id}:ACCEPTANCE_TIME_UNVERIFIED")
                continue
            accepted_at = accepted_at.astimezone(UTC)
            if accepted_at > decision_as_of:
                exclusions.append(f"{observation.observation_id}:FUTURE_ACCEPTANCE")
                continue
            if accepted_at > observation.retrieved_at:
                exclusions.append(f"{observation.observation_id}:ACCEPTANCE_AFTER_RETRIEVAL")
                continue
            definition = canonical_definition(observation.taxonomy, observation.raw_concept or observation.concept)
            canonical_metric = definition.canonical_metric if definition else None
            if canonical_metric is None:
                exclusions.append(f"{observation.observation_id}:UNKNOWN_CANONICAL_MAPPING")
                continue
            context_type = classify_context(
                period_start=observation.period_start,
                period_end=observation.period_end,
                form=observation.form,
                fiscal_period=observation.fiscal_period,
            )
            period_start = _as_utc_midnight(observation.period_start) if observation.period_start else None
            period_end = _as_utc_midnight(observation.period_end)
            filed_at = _as_utc_midnight(observation.filed_at)
            fact_digest = hashlib.sha256(
                f"{observation.observation_id}|{accession}|{getattr(metadata, 'content_hash', '')}|{accepted_at.isoformat()}".encode()
            ).hexdigest()
            try:
                certified.append(
                    CertifiedFundamentalFact(
                        fact_id=f"{observation.ticker.lower()}_{observation.observation_id}",
                        ticker=observation.ticker,
                        cik=observation.cik,
                        accession_number=accession,
                        accession_issuer_cik=(str(accession_issuer_cik).zfill(10) if accession_issuer_cik else None),
                        form=observation.form,
                        taxonomy=observation.taxonomy,
                        concept=observation.concept,
                        raw_concept=observation.raw_concept,
                        canonical_metric=canonical_metric,
                        value=observation.value,
                        unit=observation.unit,
                        period_start=period_start,
                        period_end=period_end,
                        fiscal_year=observation.fiscal_year,
                        fiscal_period=observation.fiscal_period,
                        frame=observation.frame,
                        context_id=observation.context_id,
                        context_type=context_type,
                        filed_at=filed_at,
                        accepted_at=accepted_at,
                        available_at=accepted_at,
                        retrieved_at=observation.retrieved_at,
                        source_uri=str(getattr(metadata, "source_uri", observation.source_uri)),
                        source_hash=observation.source_hash or fact_digest,
                        provider=self.provider_name,
                        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
                    )
                )
            except (ValueError, TypeError) as error:
                exclusions.append(f"{observation.observation_id}:CERTIFICATION_REJECTED:{error}")
        self.last_exclusions = tuple(sorted(set(exclusions)))
        return tuple(sorted(certified, key=lambda item: (item.canonical_metric.value if item.canonical_metric else "", item.period_end, item.fact_id)))

    def get_certified_facts(
        self, ticker: str, decision_as_of: datetime, *, metadata_provider: Any
    ) -> tuple[CertifiedFundamentalFact, ...]:
        return self.certify_observations(
            self.get_observations(ticker),
            metadata_provider=metadata_provider,
            decision_as_of=decision_as_of,
        )



