import pytest
from pydantic import ValidationError

from meridian.data.models import EvidenceRecord
from tests.retrieval_helpers import evidence_for, requirement


def test_evidence_requires_nonempty_provenance() -> None:
    payload = evidence_for(requirement()).model_dump()
    payload["source"] = ""
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(payload)
