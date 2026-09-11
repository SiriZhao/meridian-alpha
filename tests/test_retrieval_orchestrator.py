from meridian.data.retrieval_orchestrator import RetrievalOrchestrator
from tests.retrieval_helpers import NOW, SuccessProvider, requirement


def test_retrieval_orchestrator_adds_local_derived_features() -> None:
    item = requirement()
    package = RetrievalOrchestrator([SuccessProvider()], max_retries=0).retrieve(
        [item], as_of=NOW
    )
    fields = {evidence.field for evidence in package.evidence}
    assert item.field in fields
    assert {"atr14", "average_volume_20d", "sma200", "return_60d"} <= fields
    assert package.quality.blocking_missing == ()


def test_orchestrator_collects_two_numeric_sources_and_marks_conflict() -> None:
    item = requirement()
    first = SuccessProvider("primary", value="100")
    second = SuccessProvider("secondary", value="120")
    package = RetrievalOrchestrator([first, second], max_retries=0).retrieve(
        [item], as_of=NOW
    )
    assert {record.provider for record in package.evidence if record.requirement_key == item.key} >= {
        "primary",
        "secondary",
    }
    assert package.conflicts
    assert package.status.value == "SOURCE_CONFLICT"
