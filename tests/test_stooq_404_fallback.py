from email.message import Message
from urllib.error import HTTPError

from meridian.data.providers.structured import (
    HistoricalSeriesRetrievalProvider,
    StooqHistoricalProvider,
)
from meridian.data.retrieval_orchestrator import RetrievalOrchestrator
from tests.retrieval_helpers import NOW, SuccessProvider, requirement


def test_stooq_404_records_specific_failure_and_fallback_continues() -> None:
    def missing(*args, **kwargs):
        raise HTTPError("https://stooq.test", 404, "not found", Message(), None)

    stooq = HistoricalSeriesRetrievalProvider(StooqHistoricalProvider(opener=missing))
    fallback = SuccessProvider("secondary-history")
    package = RetrievalOrchestrator([stooq, fallback], max_retries=0).retrieve(
        [requirement()], as_of=NOW
    )
    assert package.provider_results[0].failure is not None
    assert package.provider_results[0].failure.reason == "STOOQ_SYMBOL_NOT_FOUND"
    assert any(item.provider == "secondary-history" for item in package.evidence)
