"""Opt-in qualitative Codex Web research with source-bound findings."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, model_validator

from meridian.config import load_policies
from meridian.data.models import (
    DataCategory,
    EvidenceRecord,
    ResearchDataRequirement,
    SourceType,
    ValidationStatus,
)
from meridian.data.providers.base import RetrievalProviderError
from meridian.research_agents.codex_json import CodexJsonClient, CodexJsonError
from meridian.runtime import policy_directory
from meridian.schemas import StableModel


class WebFinding(StableModel):
    finding: str = Field(min_length=1, max_length=3000)
    source_url: str = Field(min_length=8, max_length=2000)
    source_title: str = Field(min_length=1, max_length=500)
    published_at: date | datetime | None = None
    source_tier: str = Field(pattern=r"^(PRIMARY|REPUTABLE_MEDIA|LOW_CONFIDENCE_SENTIMENT)$")

    @model_validator(mode="after")
    def require_https_source(self) -> WebFinding:
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("WEB_FINDING_SOURCE_INVALID")
        return self


class WebResearchResponse(StableModel):
    findings: tuple[WebFinding, ...] = ()
    sources: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    confidence: Decimal = Field(ge=0, le=1)


class WebResearchAgent:
    provider_name = "codex-web-research"

    def __init__(
        self,
        *,
        client: CodexJsonClient | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.client = client or CodexJsonClient()
        self.prompt_path = prompt_path

    def supports(self, requirement: ResearchDataRequirement) -> bool:
        return requirement.allow_web_fallback and requirement.category in {
            DataCategory.NEWS,
            DataCategory.EARNINGS,
            DataCategory.CORPORATE_ACTIONS,
        }

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        prompt_path = self.prompt_path or Path(__file__).resolve().parents[3] / "prompts" / "codex_web_research_v1.md"
        if not prompt_path.is_file():
            prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "codex_web_research_v1.md"
        try:
            settings = load_policies(policy_directory()).models.research
            if settings is None:
                raise RetrievalProviderError("WEB_RESEARCH_NOT_CONFIGURED")
            prompt = prompt_path.read_text(encoding="utf-8")
            payload: dict[str, Any] = {
                "symbol": requirement.symbol,
                "questions": [requirement.field, requirement.reason],
                "time_window": requirement.lookback or "30d",
                "as_of": as_of.isoformat(),
                "prohibited_numerical_authority": True,
            }
            response = WebResearchResponse.model_validate(
                self.client.run(
                    prompt=prompt,
                    input_payload=payload,
                    output_schema=_web_research_schema(),
                    settings=settings,
                    search=True,
                )
            )
        except RetrievalProviderError:
            raise
        except (OSError, ValueError, CodexJsonError) as error:
            code = str(error) if str(error).startswith("CODEX_") else "WEB_RESEARCH_FAILED"
            raise RetrievalProviderError(code, retryable=False) from error
        records: list[EvidenceRecord] = []
        for finding in response.findings:
            timestamp = finding.published_at or as_of
            if isinstance(timestamp, date) and not isinstance(timestamp, datetime):
                timestamp = datetime.combine(timestamp, time.min, tzinfo=UTC)
            if timestamp.tzinfo is None or timestamp.utcoffset() is None or timestamp > as_of:
                continue
            records.append(
                EvidenceRecord(
                    requirement_key=requirement.key,
                    field=requirement.field,
                    category=requirement.category,
                    value={
                        "finding": finding.finding,
                        "source_title": finding.source_title,
                        "source_tier": finding.source_tier,
                        "contradictions": list(response.contradictions),
                    },
                    unit="QUALITATIVE_FINDING",
                    symbol=requirement.symbol,
                    timestamp=timestamp,
                    as_of=as_of,
                    source=finding.source_url,
                    source_type=SourceType.CODEX_WEB_RESEARCH,
                    retrieved_at=datetime.now(UTC),
                    provider=self.provider_name,
                    confidence=response.confidence,
                    is_estimate=False,
                    raw_reference=finding.source_url,
                    validation_status=ValidationStatus.DEGRADED
                    if finding.source_tier == "LOW_CONFIDENCE_SENTIMENT"
                    else ValidationStatus.PASS,
                )
            )
        if not records:
            raise RetrievalProviderError("WEB_RESEARCH_FAILED", retryable=False)
        return tuple(records)


def _web_research_schema() -> dict[str, Any]:
    finding_properties: dict[str, Any] = {
        "finding": {"type": "string"},
        "source_url": {"type": "string"},
        "source_title": {"type": "string"},
        "published_at": {"type": ["string", "null"]},
        "source_tier": {
            "type": "string",
            "enum": ["PRIMARY", "REPUTABLE_MEDIA", "LOW_CONFIDENCE_SENTIMENT"],
        },
    }
    properties: dict[str, Any] = {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": finding_properties,
                "required": list(finding_properties),
            },
        },
        "sources": {"type": "array", "items": {"type": "string"}},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }
