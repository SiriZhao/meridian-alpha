"""PIT-safe, bounded certified SEC fundamental fact contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import model_validator

from meridian.schemas import EvidencePointInTimeStatus, StableModel


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


CONCEPT_REGISTRY: Mapping[str, CanonicalMetric] = {
    "Revenues": CanonicalMetric.REVENUE,
    "RevenueFromContractWithCustomerExcludingAssessedTax": CanonicalMetric.REVENUE,
    "GrossProfit": CanonicalMetric.GROSS_PROFIT,
    "OperatingIncomeLoss": CanonicalMetric.OPERATING_INCOME,
    "NetIncomeLoss": CanonicalMetric.NET_INCOME,
    "EarningsPerShareDiluted": CanonicalMetric.DILUTED_EPS,
    "NetCashProvidedByUsedInOperatingActivities": CanonicalMetric.OPERATING_CASH_FLOW,
    "PaymentsToAcquirePropertyPlantAndEquipment": CanonicalMetric.CAPEX,
    "CashAndCashEquivalentsAtCarryingValue": CanonicalMetric.CASH_AND_EQUIVALENTS,
    "Assets": CanonicalMetric.TOTAL_ASSETS,
    "Liabilities": CanonicalMetric.TOTAL_LIABILITIES,
    "StockholdersEquity": CanonicalMetric.SHAREHOLDERS_EQUITY,
    "LongTermDebtCurrent": CanonicalMetric.LONG_TERM_DEBT,
}


class CertifiedFundamentalFact(StableModel):
    fact_id: str
    ticker: str
    cik: str
    accession_number: str
    form: str
    taxonomy: str
    concept: str
    canonical_metric: CanonicalMetric | None = None
    value: Decimal
    unit: str
    period_start: datetime | None = None
    period_end: datetime
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    context_id: str | None = None
    filed_at: datetime | None = None
    accepted_at: datetime
    available_at: datetime
    retrieved_at: datetime
    source_uri: str
    source_hash: str
    provider: str
    point_in_time_status: EvidencePointInTimeStatus

    @model_validator(mode="after")
    def pit(self):
        if (
            self.accepted_at != self.available_at
            or self.point_in_time_status is not EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
        ):
            raise ValueError("fundamental fact requires exact certified SEC acceptance time")
        if self.period_start and self.period_start >= self.period_end:
            raise ValueError("invalid duration context")
        return self


class DerivedFundamentalMetric(StableModel):
    metric: str
    value: Decimal
    input_fact_ids: tuple[str, ...]
    formula: str
    cutoff: datetime
    derived_at: datetime
    content_hash: str


class CertifiedFundamentalSnapshot(StableModel):
    ticker: str
    decision_as_of: datetime
    latest_accession: str | None = None
    facts: tuple[CertifiedFundamentalFact, ...] = ()
    derived: tuple[DerivedFundamentalMetric, ...] = ()
    missing_metrics: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()


def build_snapshot(
    ticker: str, facts: tuple[CertifiedFundamentalFact, ...], cutoff: datetime
) -> CertifiedFundamentalSnapshot:
    eligible = tuple(
        f
        for f in facts
        if f.ticker == ticker and f.available_at <= cutoff and f.canonical_metric is not None
    )
    selected: dict[CanonicalMetric, CertifiedFundamentalFact] = {}
    excluded: list[str] = []
    for fact in sorted(eligible, key=lambda f: (f.available_at, f.accession_number, f.fact_id)):
        metric = fact.canonical_metric
        if metric is None:
            continue
        current = selected.get(metric)
        if current is None or (fact.period_end, fact.available_at) > (
            current.period_end,
            current.available_at,
        ):
            selected[metric] = fact
        elif fact.unit != current.unit or fact.period_end != current.period_end:
            excluded.append(f"{fact.fact_id}:NON_COMPARABLE_CONTEXT")
    derived: list[DerivedFundamentalMetric] = []
    ocf, capex = (
        selected.get(CanonicalMetric.OPERATING_CASH_FLOW),
        selected.get(CanonicalMetric.CAPEX),
    )
    if (
        ocf
        and capex
        and ocf.unit == capex.unit
        and ocf.period_start == capex.period_start
        and ocf.period_end == capex.period_end
    ):
        ids = (ocf.fact_id, capex.fact_id)
        value = ocf.value - capex.value
        raw = f"FREE_CASH_FLOW|{value}|{ids}|{cutoff.isoformat()}"
        derived.append(
            DerivedFundamentalMetric(
                metric="FREE_CASH_FLOW",
                value=value,
                input_fact_ids=ids,
                formula="OPERATING_CASH_FLOW - CAPEX",
                cutoff=cutoff,
                derived_at=cutoff,
                content_hash=hashlib.sha256(raw.encode()).hexdigest(),
            )
        )
    missing = tuple(metric.value for metric in CanonicalMetric if metric not in selected)
    latest = max((f.accession_number for f in selected.values()), default=None)
    return CertifiedFundamentalSnapshot(
        ticker=ticker,
        decision_as_of=cutoff,
        latest_accession=latest,
        facts=tuple(selected.values()),
        derived=tuple(derived),
        missing_metrics=missing,
        excluded=tuple(excluded),
    )
