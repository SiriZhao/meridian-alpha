from datetime import UTC, datetime

from meridian.shadow_daily import run_shadow_daily


def test_shadow_daily_is_bounded_and_non_executable(tmp_path) -> None:
    report = run_shadow_daily(
        as_of=datetime(2026, 8, 28, 20, 0, tzinfo=UTC),
        output_json=tmp_path / "shadow.json",
        output_markdown=tmp_path / "shadow.md",
    )
    assert report["mode"] == "SHADOW"
    assert report["authorization"] == "SHADOW / NOT AUTHORIZED FOR ENTRY"
    assert len(report["candidate_selection"]) <= 3
    assert report["certified_signal_count"] == 0
    assert all(item["research_executable"] is False for item in report["diagnostics"])
    assert all(packet["point_in_time_status"] == "HISTORICAL_REPLAY_UNSAFE" for packet in report["evidence_packets"] if packet["items"])
    assert (tmp_path / "shadow.json").exists()
    assert (tmp_path / "shadow.md").exists()


def test_shadow_daily_surfaces_deferred_candidates() -> None:
    report = run_shadow_daily()
    assert report["deferred_candidates"]
    assert all(item["deferred_reason"] == "BUDGET_LIMIT" for item in report["deferred_candidates"])


def test_shadow_daily_has_no_live_provider_status() -> None:
    report = run_shadow_daily()
    assert report["provider_failures"] == []
    assert report["warnings"] == ["SYNTHETIC - NOT LIVE DATA", "SHADOW / NOT AUTHORIZED FOR ENTRY"]
