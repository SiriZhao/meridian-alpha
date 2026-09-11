import json
from pathlib import Path

from meridian.codex_provider import ProcessResult
from meridian.config import ResearchSettings
from meridian.research_agents.codex_json import CodexJsonClient
from meridian.research_agents.data_gap_planner import DataGapPlanner, _planner_schema


def test_gap_planner_returns_requirements_not_values(tmp_path: Path) -> None:
    prompt = tmp_path / "planner.md"
    prompt.write_text("plan fields only", encoding="utf-8")

    def runner(command, input_text, environment, cwd, timeout):
        assert "--search" not in command
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(
            json.dumps(
                {
                    "sufficient": False,
                    "missing": [
                        {
                            "symbol": "NVDA",
                            "asset_type": "EQUITY",
                            "field": "daily_ohlcv_1y",
                            "category": "PRICE_HISTORY",
                            "required": True,
                            "importance": "1",
                            "lookback": "1y",
                            "frequency": "1d",
                            "freshness_requirement": "1d",
                            "preferred_sources": ["yahoo"],
                            "allow_web_fallback": False,
                            "status": "MISSING",
                            "reason": "trend history required",
                        }
                    ],
                    "optional_missing": [],
                    "reasoning_summary": "History is missing.",
                    "recommended_queries": ["NVDA 1y daily OHLCV"],
                }
            ),
            encoding="utf-8",
        )
        return ProcessResult(returncode=0)

    settings = ResearchSettings(
        provider="codex_cli", model="codex-default", timeout_seconds=30,
        max_retries=0, debate_rounds=0, max_parallel_tickers=1,
        minimum_research_coverage=__import__("decimal").Decimal("1"), live_enabled=True,
    )
    planner = DataGapPlanner(
        client=CodexJsonClient(executable="codex-test", runner=runner), prompt_path=prompt
    )
    result = planner.analyze({"available_evidence": []}, settings)
    assert result.missing[0].field == "daily_ohlcv_1y"
    assert not hasattr(result.missing[0], "value")


def test_gap_planner_schema_uses_codex_compatible_subset() -> None:
    requirement = _planner_schema()["properties"]["missing"]["items"]
    properties = requirement["properties"]
    assert properties["lookback"] == {"type": "string"}
    assert properties["importance"] == {"type": "number"}
    assert requirement["additionalProperties"] is False
