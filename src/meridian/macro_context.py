"""Compact, optional macro evidence selection with cutoff safety."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from meridian.evidence_foundation import MacroObservation


class MacroSeries(StrEnum):
    US_2Y = "US_2Y"
    US_10Y = "US_10Y"
    TWO_TEN_SPREAD = "2S10S"
    DXY = "DXY"
    VIX = "VIX"
    OIL = "OIL"
    GOLD = "GOLD"
    FED_POLICY = "FED_POLICY"
    CPI = "CPI"
    CORE_CPI = "CORE_CPI"
    PCE = "PCE"
    UNEMPLOYMENT = "UNEMPLOYMENT"
    ISM = "ISM"


def compact_macro_context(observations: tuple[MacroObservation, ...], cutoff: datetime) -> dict[str, dict[str, str]]:
    """Expose only valid, latest observations; unknown series are omitted."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("MACRO_CUTOFF_TIMEZONE_REQUIRED")
    selected: dict[str, tuple[MacroObservation, datetime]] = {}
    for item in observations:
        available = item.available_at or item.release_at
        if available is None or available > cutoff or (item.release_at and item.release_at > cutoff) or item.observation_period > cutoff.date():
            continue
        prior = selected.get(item.series_id)
        if prior is not None and prior[1] == available and prior[0].value != item.value:
            raise ValueError("MACRO_SOURCE_CONFLICT")
        if prior is None or prior[1] < available:
            selected[item.series_id] = (item, available)
    return {
        series: {
            "value": str(item.value), "unit": item.units,
            "observation_period": item.observation_period.isoformat(),
            "available_at": available.isoformat(), "source": item.source,
            "provenance": item.point_in_time_status.value,
        }
        for series, (item, available) in sorted(selected.items())
    }
