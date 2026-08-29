"""Typed development security metadata; not a live security master."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class AssetType(StrEnum):
    EQUITY = "EQUITY"
    DIVERSIFIED_ETF = "DIVERSIFIED_ETF"


@dataclass(frozen=True)
class SecurityMetadata:
    ticker: str
    asset_type: AssetType
    sector: str | None = None
    industry: str | None = None


class SecurityMetadataProvider(Protocol):
    def get(self, ticker: str) -> SecurityMetadata | None: ...


class DevelopmentSecurityMetadataRegistry:
    """Explicit development fixture; never treated as production metadata."""

    _items = {
        "AAPL": SecurityMetadata(
            "AAPL", AssetType.EQUITY, "Information Technology", "Technology Hardware"
        ),
        "MSFT": SecurityMetadata("MSFT", AssetType.EQUITY, "Information Technology", "Software"),
        "NVDA": SecurityMetadata(
            "NVDA", AssetType.EQUITY, "Information Technology", "Semiconductors"
        ),
        "SPY": SecurityMetadata("SPY", AssetType.DIVERSIFIED_ETF, None, None),
    }

    def get(self, ticker: str) -> SecurityMetadata | None:
        return self._items.get(ticker)
