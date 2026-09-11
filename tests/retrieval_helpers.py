from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.data.models import (
    DataCategory,
    EvidenceRecord,
    ResearchDataRequirement,
    SourceType,
    ValidationStatus,
)

NOW = datetime(2026, 9, 10, 20, tzinfo=UTC)


def requirement(
    *,
    symbol: str = "NVDA",
    field: str = "daily_ohlcv_1y",
    category: DataCategory = DataCategory.PRICE_HISTORY,
    required: bool = True,
) -> ResearchDataRequirement:
    return ResearchDataRequirement(
        symbol=symbol,
        asset_type="EQUITY",
        field=field,
        category=category,
        required=required,
        lookback="1y",
        frequency="1d",
        freshness_requirement="1d",
        reason="test requirement",
    )


def history_value(count: int = 260) -> list[dict[str, str]]:
    start = NOW - timedelta(days=count + 10)
    rows = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        close = Decimal("100") + Decimal(index) / Decimal("10")
        rows.append(
            {
                "session": timestamp.date().isoformat(),
                "open": str(close - Decimal("0.5")),
                "high": str(close + Decimal("1")),
                "low": str(close - Decimal("1")),
                "close": str(close),
                "volume": str(1_000_000 + index),
                "observed_at": timestamp.isoformat(),
            }
        )
    return rows


def evidence_for(
    item: ResearchDataRequirement,
    *,
    provider: str = "fixture-provider",
    value: Any | None = None,
    validation: ValidationStatus = ValidationStatus.PASS,
) -> EvidenceRecord:
    return EvidenceRecord(
        requirement_key=item.key,
        field=item.field,
        category=item.category,
        value=history_value() if value is None else value,
        unit="OHLCV" if item.category is DataCategory.PRICE_HISTORY else "VALUE",
        symbol=item.symbol,
        timestamp=NOW - timedelta(days=1),
        as_of=NOW,
        source=f"https://example.test/{provider}/{item.symbol}",
        source_type=SourceType.STRUCTURED_PROVIDER,
        retrieved_at=NOW,
        provider=provider,
        confidence=Decimal("0.9"),
        raw_reference=f"{provider}:{item.key}",
        validation_status=validation,
    )


class SuccessProvider:
    def __init__(self, name: str = "success", *, value: Any | None = None) -> None:
        self.provider_name = name
        self.value = value
        self.calls = 0

    def supports(self, requirement: ResearchDataRequirement) -> bool:
        return requirement.category in {DataCategory.PRICE_HISTORY, DataCategory.BENCHMARK}

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        self.calls += 1
        evidence = evidence_for(requirement, provider=self.provider_name, value=self.value)
        return (evidence.model_copy(update={"as_of": as_of}),)


def research_request(*, cutoff: datetime = NOW) -> DailyResearchInput:
    return DailyResearchInput(
        parent_run_id="daily-test",
        analysis_cutoff=cutoff,
        mode="LIVE",
        snapshot_reference="a" * 64,
        market_reference="b" * 64,
        policy_reference="c" * 64,
        provider="codex_cli",
        model="codex-default",
        observations=(
            PublicResearchObservation(
                ticker="NVDA",
                observed_at=cutoff - timedelta(minutes=1),
                price=Decimal("100"),
                daily_return=Decimal("0.01"),
                reference="d" * 64,
            ),
        ),
        freshness_status="PASS",
        provider_provenance={"NVDA": "fixture"},
    )
