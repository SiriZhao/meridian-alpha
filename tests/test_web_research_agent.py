from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from meridian.data.models import (
    DataCategory,
    ResearchDataRequirement,
    SourceType,
)
from meridian.research_agents.codex_json import CodexJsonClient
from meridian.research_agents.web_research_agent import WebResearchAgent


class DateOnlyWebClient:
    def run(self, **kwargs):
        assert kwargs["search"] is True
        return {
            "findings": [
                {
                    "finding": "The company published a material product update.",
                    "source_url": "https://example.com/investor-relations/update",
                    "source_title": "Official company update",
                    "published_at": "2026-09-03",
                    "source_tier": "PRIMARY",
                }
            ],
            "sources": ["https://example.com/investor-relations/update"],
            "contradictions": [],
            "confidence": 0.9,
        }


def test_date_only_publication_keeps_source_bound_qualitative_finding(
    monkeypatch,
) -> None:
    from meridian.research_agents import web_research_agent as module

    settings = type("Policies", (), {"models": type("Models", (), {"research": object()})()})()
    monkeypatch.setattr(module, "load_policies", lambda _path: settings)
    agent = WebResearchAgent(client=cast(CodexJsonClient, DateOnlyWebClient()))
    requirement = ResearchDataRequirement(
        symbol="NVDA",
        asset_type="EQUITY",
        field="material_events",
        category=DataCategory.NEWS,
        required=False,
        importance=Decimal("0.5"),
        lookback="30d",
        allow_web_fallback=True,
        reason="Optional material-event context",
    )

    records = agent.retrieve(
        requirement, as_of=datetime(2026, 9, 10, 23, tzinfo=UTC)
    )

    assert len(records) == 1
    assert records[0].timestamp == datetime(2026, 9, 3, tzinfo=UTC)
    assert records[0].source_type is SourceType.CODEX_WEB_RESEARCH
    assert records[0].source == "https://example.com/investor-relations/update"
