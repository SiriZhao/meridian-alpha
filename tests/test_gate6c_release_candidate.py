from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.execution_quote_providers import (
    AlpacaExecutionQuoteProvider,
    PolygonExecutionQuoteProvider,
    provider_preflight,
)
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.identity_certification import load_verified_security_certificates

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 31, 14, 30, tzinfo=UTC)


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self.payload


def test_real_host_template_is_valid_and_uses_verified_runtime_identity() -> None:
    envelope = HostAccountSnapshotEnvelope.model_validate_json(
        (ROOT / "schemas" / "examples" / "real-host-envelope-template.json").read_text()
    )
    master = load_verified_security_certificates(ROOT / "reports" / "gate4f-security-master.json")
    snapshot = normalize_host_snapshot(
        envelope,
        security_master=master,
        trusted_now=envelope.retrieved_at,
        replay=True,
    )
    assert snapshot.provider == "host-envelope"
    assert master.authoritative_count() == 11


def test_quote_preflight_is_sanitized_when_credentials_are_absent(monkeypatch: Any) -> None:
    for key in (
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "POLYGON_API_KEY",
        "POLYGON_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    results = provider_preflight()
    assert {item.provider for item in results} == {"alpaca-market-data", "polygon-market-data"}
    assert all(not item.configured and not item.certificate_eligible for item in results)
    assert "secret" not in json.dumps([item.model_dump(mode="json") for item in results]).lower()


def test_alpaca_candidate_is_read_only_and_parses_quote_and_trade(monkeypatch: Any) -> None:
    monkeypatch.setenv("APCA_API_KEY_ID", "local-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "local-secret")
    payloads = iter(
        [
            {"quote": {"bp": "199.90", "ap": "200.10", "t": NOW.isoformat()}},
            {"trade": {"p": "200.00", "t": NOW.isoformat()}},
        ]
    )
    provider = AlpacaExecutionQuoteProvider(opener=lambda *_args, **_kwargs: _Response(next(payloads)), clock=lambda: NOW)
    quote = provider.get_quote("AAPL", as_of=NOW)
    assert quote.bid == Decimal("199.90") and quote.ask == Decimal("200.10") and quote.last == Decimal("200")
    assert quote.provider == "alpaca-market-data"
    assert provider.capabilities.execution_quote_grade is False


def test_polygon_candidate_is_read_only_and_parses_nanosecond_timestamps(monkeypatch: Any) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "local-key")
    epoch_ns = int(NOW.timestamp() * 1_000_000_000)
    payloads = iter(
        [
            {"results": [{"bid_price": 199.9, "ask_price": 200.1, "sip_timestamp": epoch_ns}]},
            {"results": {"price": 200.0, "sip_timestamp": epoch_ns}},
        ]
    )
    provider = PolygonExecutionQuoteProvider(opener=lambda *_args, **_kwargs: _Response(next(payloads)), clock=lambda: NOW)
    quote = provider.get_quote("AAPL", as_of=NOW)
    assert quote.bid == Decimal("199.9") and quote.ask == Decimal("200.1") and quote.last == Decimal("200")
    assert quote.provider == "polygon-market-data"
    assert provider.capabilities.execution_quote_grade is False
