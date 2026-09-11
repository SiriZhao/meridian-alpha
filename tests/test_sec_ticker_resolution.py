import json
from datetime import UTC, datetime

import pytest

from meridian.fundamentals import SECTickerResolver

T = datetime(2026, 9, 11, tzinfo=UTC)


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_sec_ticker_resolver_exact_match_is_cached() -> None:
    calls = 0

    def opener(request, timeout: int):
        nonlocal calls
        _ = request, timeout
        calls += 1
        return Response({"0": {"ticker": "NVDA", "title": "NVIDIA CORP", "cik_str": 1045810}})

    resolver = SECTickerResolver(opener=opener, clock=lambda: T)
    assert resolver.resolve("nvda") == ("0001045810", "NVIDIA CORP", None, T)
    assert resolver.resolve("NVDA") == ("0001045810", "NVIDIA CORP", None, T)
    assert calls == 1


@pytest.mark.parametrize("rows", [
    {},
    {"0": {"ticker": "META", "title": "Meta A", "cik_str": 1}, "1": {"ticker": "META", "title": "Meta B", "cik_str": 2}},
])
def test_sec_ticker_resolver_rejects_missing_or_ambiguous_symbols(rows: object) -> None:
    resolver = SECTickerResolver(opener=lambda request, timeout: Response(rows), clock=lambda: T)
    with pytest.raises(ValueError, match="SEC_TICKER_AMBIGUOUS_OR_UNAVAILABLE"):
        resolver.resolve("META")
