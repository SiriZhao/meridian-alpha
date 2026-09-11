from datetime import datetime

from meridian.data.models import EvidenceRecord, ResearchDataRequirement
from meridian.data.providers.base import RetrievalProviderError
from meridian.data.retrieval_orchestrator import RetrievalOrchestrator
from tests.retrieval_helpers import NOW, SuccessProvider, requirement


class FailedProvider:
    provider_name = "failed-primary"

    def supports(self, requirement: ResearchDataRequirement) -> bool:
        return True

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        raise RetrievalProviderError("PRIMARY_TIMEOUT", retryable=False)


def test_provider_failure_falls_through_to_next_provider() -> None:
    fallback = SuccessProvider("fallback")
    package = RetrievalOrchestrator(
        [FailedProvider(), fallback], max_retries=0
    ).retrieve([requirement()], as_of=NOW)
    assert fallback.calls == 1
    assert any(item.provider == "fallback" for item in package.evidence)
    assert package.provider_results[0].failure is not None
    assert package.provider_results[0].failure.reason == "PRIMARY_TIMEOUT"
