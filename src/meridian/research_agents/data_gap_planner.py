"""Codex data-gap planner: it requests fields and is unable to return market values."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field, ValidationError, model_validator

from meridian.config import ResearchSettings
from meridian.data.models import ResearchDataRequirement
from meridian.research_agents.codex_json import CodexJsonClient, CodexJsonError
from meridian.schemas import StableModel


class DataGapPlan(StableModel):
    sufficient: bool
    missing: tuple[ResearchDataRequirement, ...] = ()
    optional_missing: tuple[ResearchDataRequirement, ...] = ()
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    recommended_queries: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_sufficiency(self) -> DataGapPlan:
        if self.sufficient and any(item.required for item in self.missing):
            raise ValueError("PLANNER_SUFFICIENT_WITH_BLOCKING_MISSING")
        return self


class GapPlanner(Protocol):
    def analyze(
        self, context: Mapping[str, Any], settings: ResearchSettings
    ) -> DataGapPlan: ...


class DataGapPlanner:
    def __init__(
        self,
        *,
        client: CodexJsonClient | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.client = client or CodexJsonClient()
        self.prompt_path = prompt_path

    def analyze(
        self, context: Mapping[str, Any], settings: ResearchSettings
    ) -> DataGapPlan:
        prompt_path = self.prompt_path or Path(__file__).resolve().parents[3] / "prompts" / "codex_data_gap_planner_v1.md"
        if not prompt_path.is_file():
            prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "codex_data_gap_planner_v1.md"
        try:
            prompt = prompt_path.read_text(encoding="utf-8")
            payload = self.client.run(
                prompt=prompt,
                input_payload=context,
                output_schema=_planner_schema(),
                settings=settings,
                search=False,
            )
            return DataGapPlan.model_validate(payload)
        except ValidationError as error:
            fields = ";".join(
                f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
                for item in error.errors(include_url=False, include_context=False, include_input=False)
            )[:600]
            raise RuntimeError(f"GPT_PLANNER_FAILED[{fields}]") from error
        except (OSError, ValueError, CodexJsonError) as error:
            code = str(error) if str(error).startswith("CODEX_") else "GPT_PLANNER_FAILED"
            raise RuntimeError(code) from error


def _requirement_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        # Keep the Codex-facing schema to the stable structured-output subset.
        # Pydantic applies the stricter patterns, lengths, and numeric ranges.
        "symbol": {"type": "string"},
        "asset_type": {"type": "string"},
        "field": {"type": "string"},
        "category": {"type": "string", "enum": [
            "PRICE_HISTORY", "VOLUME_HISTORY", "MARKET_SNAPSHOT", "VOLATILITY",
            "TECHNICAL", "FUNDAMENTALS", "VALUATION", "EARNINGS",
            "CORPORATE_ACTIONS", "NEWS", "MACRO", "RATES", "BENCHMARK",
            "MARKET_REGIME", "PORTFOLIO_CONTEXT", "INVESTMENT_HORIZON",
        ]},
        "required": {"type": "boolean"},
        "importance": {"type": "number"},
        "lookback": {"type": "string"},
        "frequency": {"type": "string"},
        "freshness_requirement": {"type": "string"},
        "preferred_sources": {"type": "array", "items": {"type": "string"}},
        "allow_web_fallback": {"type": "boolean"},
        "status": {
            "type": "string",
            "enum": ["MISSING", "AVAILABLE", "RETRIEVED", "FAILED", "CONFLICT"],
        },
        "reason": {"type": "string"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _planner_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "sufficient": {"type": "boolean"},
        "missing": {"type": "array", "items": _requirement_schema()},
        "optional_missing": {"type": "array", "items": _requirement_schema()},
        "reasoning_summary": {"type": "string"},
        "recommended_queries": {"type": "array", "items": {"type": "string"}},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }
