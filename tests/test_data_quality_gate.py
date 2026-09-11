from meridian.data.models import DataStatus
from meridian.data.retrieval_orchestrator import DataQualityGate
from tests.retrieval_helpers import NOW, evidence_for, requirement


def test_quality_gate_preserves_blocking_requirements() -> None:
    required = requirement()
    optional = requirement(field="latest_fundamentals", required=False)
    quality, status = DataQualityGate().evaluate(
        [required, optional], [evidence_for(required)], (), as_of=NOW
    )
    assert not quality.blocking_missing
    assert status is DataStatus.DATA_DEGRADED


def test_quality_gate_blocks_missing_required() -> None:
    required = requirement()
    quality, status = DataQualityGate().evaluate([required], [], (), as_of=NOW)
    assert required.key in quality.blocking_missing
    assert status is DataStatus.NUMERICAL_DATA_MISSING
