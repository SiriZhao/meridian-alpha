from __future__ import annotations

import json
from pathlib import Path

from meridian.application import MeridianApplicationService
from meridian.runtime import RuntimePaths


def test_latest_report_is_fixed_redacted_summary(tmp_path: Path) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    report = paths.reports / "2026-09-02" / "run" / "daily.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "run_id": "run",
                "status": "DRAFT",
                "execution": "MANUAL",
                "broker_submission": "DISABLED",
                "account_number": "must-not-leak",
                "orders": [{"ticker": "AAPL"}],
            }
        ),
        encoding="utf-8",
    )
    result = MeridianApplicationService(paths).latest_report()
    assert result["found"] is True
    report_payload = result["report"]
    assert isinstance(report_payload, dict)
    assert "account_number" not in report_payload
    assert "orders" not in report_payload
    assert result["broker_submission"] == "DISABLED"
