from decimal import Decimal

import pytest

from meridian.config import EvidenceCompletenessPolicy


def test_evidence_age_policy_rejects_negative_age() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        EvidenceCompletenessPolicy(
            minimum_total_items=0,
            minimum_distinct_sources=0,
            maximum_age_by_type={"news": -1},
            minimum_point_in_time_quality=Decimal("0"),
        )


def test_evidence_age_policy_rejects_blank_type() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        EvidenceCompletenessPolicy(
            minimum_total_items=0,
            minimum_distinct_sources=0,
            maximum_age_by_type={" ": 60},
            minimum_point_in_time_quality=Decimal("0"),
        )
