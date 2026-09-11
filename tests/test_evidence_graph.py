from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.astra_research import MeridianResearchResult, ResearchIntent
from meridian.event_evidence import EventType, QualitativeEventEvidence
from meridian.evidence_foundation import EvidencePITCertification, MacroObservation
from meridian.evidence_graph import (
    EvidenceGraph,
    EvidenceGraphClaim,
    EvidenceGraphNode,
    EvidenceGraphRelation,
    EvidenceNodeType,
    EvidenceRelationType,
)
from meridian.macro_context import compact_macro_context
from meridian.mcp_server import event_evidence, macro_context

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def test_graph_rejects_dangling_evidence_and_node_references() -> None:
    with pytest.raises(ValueError, match="DANGLING_EVIDENCE"):
        EvidenceGraph(
            nodes=(EvidenceGraphNode(node_id="claim", node_type=EvidenceNodeType.CLAIM, statement="x"),),
            claims=(EvidenceGraphClaim(claim_id="c", claim_type="FACT", statement="x", confidence=0.5, supporting_evidence_ids=("missing",)),),
        )
    with pytest.raises(ValueError, match="DANGLING_NODE"):
        EvidenceGraph(
            nodes=(EvidenceGraphNode(node_id="claim", node_type=EvidenceNodeType.CLAIM, statement="x"),),
            relationships=(EvidenceGraphRelation(from_node_id="claim", to_node_id="missing", relation=EvidenceRelationType.SUPPORTED_BY),),
        )


def test_result_rejects_graph_evidence_not_in_research_evidence() -> None:
    graph = EvidenceGraph(nodes=(EvidenceGraphNode(node_id="e", node_type=EvidenceNodeType.EVIDENCE, statement="source", evidence_id="unknown"),))
    with pytest.raises(ValueError, match="RESEARCH_GRAPH_EVIDENCE_UNKNOWN"):
        MeridianResearchResult(subject="NVDA", analysis_cutoff=NOW, research_question="q", intent=ResearchIntent.COMPANY_RESEARCH, evidence_graph=graph)


def test_event_and_macro_are_cutoff_bounded_and_source_bearing() -> None:
    event = QualitativeEventEvidence(
        ticker="NVDA", headline="Company filing released", source="SEC", published_at=NOW - timedelta(hours=1),
        retrieved_at=NOW, analysis_cutoff=NOW, event_type=EventType.EARNINGS,
        source_reference="https://www.sec.gov/Archives/example", quality="PRIMARY", provenance="SEC accession",
    )
    assert event.event_id and event.event_type is EventType.EARNINGS
    with pytest.raises(ValueError, match="EVENT_AFTER_CUTOFF"):
        event.model_copy(update={"published_at": NOW + timedelta(seconds=1)}).model_validate(event.model_copy(update={"published_at": NOW + timedelta(seconds=1)}).model_dump())
    macro = MacroObservation(series_id="US_10Y", observation_period=date(2026, 9, 10), value=Decimal("4.1"), units="percent", release_at=NOW - timedelta(hours=2), available_at=NOW - timedelta(hours=2), retrieved_at=NOW, source="fixture", point_in_time_status=EvidencePITCertification.UNVERIFIED)
    future = macro.model_copy(update={"series_id": "VIX", "available_at": NOW + timedelta(seconds=1), "release_at": NOW + timedelta(seconds=1)})
    context = compact_macro_context((macro, future), NOW)
    assert set(context) == {"US_10Y"} and context["US_10Y"]["source"] == "fixture"


def test_event_and_macro_mcp_tools_are_read_only_and_fail_explicitly() -> None:
    event = QualitativeEventEvidence(
        ticker="NVDA", headline="Primary filing", source="SEC", published_at=NOW - timedelta(hours=1),
        retrieved_at=NOW, analysis_cutoff=NOW, event_type=EventType.REGULATORY,
        source_reference="https://www.sec.gov/example", quality="PRIMARY", provenance="accession fixture",
    )
    event_result = event_evidence([event], NOW)
    assert event_result["status"] == "AVAILABLE"
    assert event_result["execution_authority"] == "NONE"
    macro_result = macro_context([], NOW)
    assert macro_result["status"] == "UNAVAILABLE"
    assert macro_result["errors"] == ["MACRO_CONTEXT_MISSING"]
    assert macro_result["execution_authority"] == "NONE"
