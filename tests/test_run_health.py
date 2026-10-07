from typing import cast

from meridian.run_health import STAGES, build_run_health


def test_paper_health_does_not_invent_unrecorded_canonical_stages():
    health = build_run_health({
        "paper_run_id": "paper-daily-1",
        "canonical_run_id": "daily-1",
        "analysis_time": "2026-09-12T00:00:00+00:00",
        "status": "PAPER_BLOCKED",
    })
    assert health["canonical_run_id"] == "daily-1"
    assert health["stage_source"] == "CANONICAL_RUN"
    stages = cast(list[dict[str, object]], health["stages"])
    assert len(stages) == len(STAGES)
    assert all(stage["status"] == "NOT_RECORDED" for stage in stages)
    assert all(stage["execution_state"] == "UNKNOWN" for stage in stages)
    assert all(stage["source_run_id"] is None for stage in stages)
