"""Resource-aware, deterministic research-universe scheduling.

This module controls research breadth only. It does not alter signals, weights,
orders, gates, or execution authority.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from meridian.config import ResearchBudgetPolicy
from meridian.schemas import MarketSnapshot, StableModel

_GIB = 1024**3


@dataclass(frozen=True)
class ResearchResourceProfile:
    """Only coarse capacity facts are retained; no host identifier is exposed."""

    cpu_count: int
    memory_bytes: int | None
    source: str = "runtime"

    @classmethod
    def detect(cls) -> ResearchResourceProfile:
        return cls(
            cpu_count=max(1, os.cpu_count() or 1),
            memory_bytes=_physical_memory_bytes(),
        )

    def effective_ticker_limit(self, hard_limit: int) -> int:
        """Lower, but never raise, the configured hard research budget."""
        if self.cpu_count <= 2 or (
            self.memory_bytes is not None and self.memory_bytes < 4 * _GIB
        ):
            divisor = 4
        elif self.cpu_count <= 4 or (
            self.memory_bytes is not None and self.memory_bytes < 8 * _GIB
        ):
            divisor = 2
        elif self.cpu_count <= 8 or (
            self.memory_bytes is not None and self.memory_bytes < 16 * _GIB
        ):
            divisor = 4 / 3
        else:
            divisor = 1
        return max(1, min(hard_limit, int(hard_limit / divisor)))


class ResearchUniversePlan(StableModel):
    eligible_universe: tuple[str, ...]
    research_universe: tuple[str, ...]
    deep_analysis_universe: tuple[str, ...]
    mode: Literal["full", "reduced"]
    original_count: int = Field(ge=0)
    research_count: int = Field(ge=0)
    deep_analysis_count: int = Field(ge=0)
    policy_limit: int = Field(ge=1)
    resource_limit: int = Field(ge=1)
    selection_basis: Literal["FULL_UNIVERSE", "HIGH_LIQUIDITY"]
    resource_cpu_count: int = Field(ge=1)
    resource_memory_gib: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_layers(self) -> ResearchUniversePlan:
        eligible = set(self.eligible_universe)
        research = set(self.research_universe)
        deep = set(self.deep_analysis_universe)
        if not deep.issubset(research) or not research.issubset(eligible):
            raise ValueError("research universe layers must be nested")
        if (
            self.original_count != len(self.eligible_universe)
            or self.research_count != len(self.research_universe)
            or self.deep_analysis_count != len(self.deep_analysis_universe)
        ):
            raise ValueError("research universe counts do not match their layers")
        if self.deep_analysis_count > min(self.policy_limit, self.resource_limit):
            raise ValueError("deep analysis universe exceeds effective budget")
        if (self.mode == "full") != (self.deep_analysis_count == self.original_count):
            raise ValueError("research universe mode does not match selected breadth")
        return self


class ResearchUniverseScheduler:
    """Build nested research universes without changing investment decisions."""

    def __init__(self, resource_profile: ResearchResourceProfile | None = None) -> None:
        self.resource_profile = resource_profile or ResearchResourceProfile.detect()

    def plan(
        self,
        eligible_tickers: Sequence[str],
        quotes: Mapping[str, MarketSnapshot],
        *,
        policy: ResearchBudgetPolicy,
        existing_holdings: Sequence[str] = (),
    ) -> ResearchUniversePlan:
        eligible = tuple(sorted({ticker.upper() for ticker in eligible_tickers if ticker.upper() in quotes}))
        held = {ticker.upper() for ticker in existing_holdings if ticker.upper() in eligible}
        effective_limit = self.resource_profile.effective_ticker_limit(
            policy.max_graph_tickers_per_run
        )
        if policy.always_review_existing_holdings and len(held) > effective_limit:
            raise ValueError("research budget cannot review every required holding")

        ranked = tuple(
            sorted(
                eligible,
                key=lambda ticker: (
                    0 if ticker in held and policy.always_review_existing_holdings else 1,
                    -(quotes[ticker].last * quotes[ticker].volume),
                    ticker,
                ),
            )
        )
        research = ranked[: policy.max_graph_tickers_per_run]
        deep = research[:effective_limit]
        mode: Literal["full", "reduced"] = "full" if len(deep) == len(eligible) else "reduced"
        memory_gib = (
            Decimal(self.resource_profile.memory_bytes) / Decimal(_GIB)
            if self.resource_profile.memory_bytes is not None
            else None
        )
        return ResearchUniversePlan(
            eligible_universe=eligible,
            research_universe=research,
            deep_analysis_universe=deep,
            mode=mode,
            original_count=len(eligible),
            research_count=len(research),
            deep_analysis_count=len(deep),
            policy_limit=policy.max_graph_tickers_per_run,
            resource_limit=effective_limit,
            selection_basis="FULL_UNIVERSE" if mode == "full" else "HIGH_LIQUIDITY",
            resource_cpu_count=self.resource_profile.cpu_count,
            resource_memory_gib=memory_gib,
        )


def _physical_memory_bytes() -> int | None:
    if sys.platform == "win32":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError, ValueError):
            return None
    try:
        sysconf = cast(Any, os).sysconf
        page_size = sysconf("SC_PAGE_SIZE")
        pages = sysconf("SC_PHYS_PAGES")
        return int(page_size * pages)
    except (AttributeError, OSError, TypeError, ValueError):
        return None
