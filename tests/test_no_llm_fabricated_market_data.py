import pytest
from pydantic import ValidationError

from meridian.data.models import (
    DataCategory,
    EvidenceRecord,
    SourceType,
)
from tests.retrieval_helpers import evidence_for, requirement


def test_codex_web_cannot_supply_market_price() -> None:
    item = requirement(field="current_market_snapshot", category=DataCategory.MARKET_SNAPSHOT)
    payload = evidence_for(item, value="210").model_dump()
    payload["source_type"] = SourceType.CODEX_WEB_RESEARCH
    with pytest.raises(ValidationError, match="WEB_RESEARCH_CANNOT_SUPPLY_NUMERICAL_EVIDENCE"):
        EvidenceRecord.model_validate(payload)
