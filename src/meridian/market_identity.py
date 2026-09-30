"""Canonical semantic identity and reconciliation for market snapshots."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_EPHEMERAL_FIELDS = frozenset({
    "timestamp", "observed_at", "available_at", "retrieved_at", "received_at",
    "generated_at", "freshness_state", "freshness", "freshness_reason", "age_seconds",
    "stale_age_seconds", "quality_status", "execution_quote_grade",
})


class MarketConsistencyStatus(StrEnum):
    """Relationship between a research snapshot and the resume snapshot."""

    EXACT = "EXACT"
    REVALIDATED = "REVALIDATED"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class MarketConsistency:
    status: MarketConsistencyStatus
    old_reference: str | None
    new_reference: str | None
    reason: str
    max_price_change_fraction: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "old_reference": self.old_reference,
            "new_reference": self.new_reference,
            "reason": self.reason,
            "max_price_change_fraction": self.max_price_change_fraction,
        }

def canonical_quote_payload(value: Any) -> Any:
    """Return deterministic quote content with operational metadata removed."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): canonical_quote_payload(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0])) if str(key) not in _EPHEMERAL_FIELDS}
    if isinstance(value, (list, tuple)):
        return [canonical_quote_payload(item) for item in value]
    return value

def canonical_market_reference(quotes: Mapping[str, Any] | Any) -> str:
    """Hash one canonical semantic market snapshot with stable serialization."""
    encoded = json.dumps(canonical_quote_payload(quotes), ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_quote_payload(value: Any) -> Any:
    payload = canonical_quote_payload(value)
    if isinstance(payload, Mapping):
        return {
            key: item
            for key, item in payload.items()
            if key not in {"last", "daily_return", "change", "change_percent"}
        }
    return payload


def compare_market_snapshots(
    old_quotes: Mapping[str, Any] | Any,
    new_quotes: Mapping[str, Any] | Any,
    *,
    max_price_change_fraction: float = 0.005,
) -> MarketConsistency:
    """Classify resume compatibility without silently accepting stale research."""
    old_reference = canonical_market_reference(old_quotes)
    new_reference = canonical_market_reference(new_quotes)
    if old_reference == new_reference:
        return MarketConsistency(MarketConsistencyStatus.EXACT, old_reference, new_reference, "SEMANTIC_REFERENCE_MATCH")
    if not isinstance(old_quotes, Mapping) or not isinstance(new_quotes, Mapping):
        return MarketConsistency(MarketConsistencyStatus.INVALID, old_reference, new_reference, "QUOTE_MAPPING_REQUIRED")
    if set(old_quotes) != set(new_quotes):
        return MarketConsistency(MarketConsistencyStatus.REFRESH_REQUIRED, old_reference, new_reference, "SYMBOL_UNIVERSE_CHANGED")
    max_change = 0.0
    for symbol in sorted(old_quotes):
        old_payload = canonical_quote_payload(old_quotes[symbol])
        new_payload = canonical_quote_payload(new_quotes[symbol])
        if _semantic_quote_payload(old_payload) != _semantic_quote_payload(new_payload):
            return MarketConsistency(MarketConsistencyStatus.REFRESH_REQUIRED, old_reference, new_reference, "MATERIAL_MARKET_REFERENCE_CHANGED")
        try:
            old_price = float(old_payload["last"])
            new_price = float(new_payload["last"])
        except (KeyError, TypeError, ValueError):
            return MarketConsistency(MarketConsistencyStatus.INVALID, old_reference, new_reference, "QUOTE_PRICE_MISSING")
        if old_price <= 0 or new_price <= 0:
            return MarketConsistency(MarketConsistencyStatus.INVALID, old_reference, new_reference, "QUOTE_PRICE_INVALID")
        max_change = max(max_change, abs(new_price - old_price) / old_price)
    if max_change <= max_price_change_fraction:
        return MarketConsistency(MarketConsistencyStatus.REVALIDATED, old_reference, new_reference, "PRICE_ONLY_MOVE_WITHIN_REVALIDATION_POLICY", max_change)
    return MarketConsistency(MarketConsistencyStatus.REFRESH_REQUIRED, old_reference, new_reference, "PRICE_MOVE_EXCEEDS_REVALIDATION_POLICY", max_change)
