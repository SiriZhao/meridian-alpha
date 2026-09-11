from decimal import Decimal

from meridian.data.models import DataCategory
from meridian.data.retrieval_orchestrator import detect_source_conflicts
from tests.retrieval_helpers import evidence_for, requirement


def test_material_numeric_disagreement_is_source_conflict() -> None:
    item = requirement(field="current_market_snapshot", category=DataCategory.MARKET_SNAPSHOT)
    left = evidence_for(item, provider="a", value="210")
    right = evidence_for(item, provider="b", value="185")
    conflicts = detect_source_conflicts([left, right], price_tolerance=Decimal("0.01"))
    assert conflicts and conflicts[0].status == "SOURCE_CONFLICT"
