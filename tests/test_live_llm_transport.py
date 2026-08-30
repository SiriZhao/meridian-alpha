import json
from datetime import UTC, datetime

import pytest

from meridian.config import load_policies
from meridian.research import (
    DeepSeekGroundedResearchNormalizer,
    GraphResearchSummary,
    GroundedResearchStatus,
    PointInTimeStatus,
    ResearchEvidencePacket,
    ResearchStatus,
)
from meridian.schemas import EvidenceItem

AS_OF = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def summary() -> GraphResearchSummary:
    return GraphResearchSummary(
        ticker="AAPL", as_of=AS_OF, status=ResearchStatus.GRAPH_SUMMARY_ONLY,
        provider="fixture", model="none", framework_version="1", started_at=AS_OF,
        completed_at=AS_OF, point_in_time_status=PointInTimeStatus.LIVE_RESEARCH_OK,
    )


def packet() -> ResearchEvidencePacket:
    item = EvidenceItem(
        ticker="AAPL", provider="sec-edgar-accession-certified", source="https://www.sec.gov/Archives/example",
        observed_at=AS_OF, available_at=AS_OF, evidence_type="sec_fact",
        point_in_time_status="CERTIFIED_HISTORICAL_PIT", summary="Certified filing fact.",
    )
    return ResearchEvidencePacket(
        packet_id="certified-aapl", ticker="AAPL", as_of=AS_OF, created_at=AS_OF,
        items=(item,), point_in_time_status="CERTIFIED_HISTORICAL_PIT",
    )


def settings():
    research = load_policies(__import__("pathlib").Path(__file__).parents[1] / "policies").models.research
    assert research is not None
    return research.model_copy(
        update={"live_enabled": True}
    )


def response(content: object, status: int = 200) -> tuple[int, bytes, dict[str, str]]:
    return status, json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}).encode(), {}


def normalizer(monkeypatch: pytest.MonkeyPatch, http_post):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    return DeepSeekGroundedResearchNormalizer(settings(), clock=lambda: AS_OF, http_post=http_post)


def available_payload(evidence_id: str) -> dict[str, object]:
    return {
        "status": "AVAILABLE", "reason": "Certified filing supports the bounded assessment.",
        "direction": "BULLISH", "conviction": "0.60", "thesis": "Filing-backed fixture thesis.",
        "risks": ["Fixture risk"], "cited_evidence_ids": [evidence_id],
    }


@pytest.mark.parametrize("content", [
    pytest.param(lambda item_id: json.dumps(available_payload(item_id)), id="json"),
    pytest.param(lambda item_id: "```json\n" + json.dumps(available_payload(item_id)) + "\n```", id="fenced-json"),
])
def test_valid_compatible_response_creates_grounded_signal(monkeypatch, content) -> None:
    evidence = packet()
    result = normalizer(monkeypatch, lambda *_: response(content(evidence.items[0].stable_id))).normalize(summary(), evidence, AS_OF)
    assert result.status is GroundedResearchStatus.AVAILABLE
    assert result.signal is not None
    assert "GROUNDING_RESULT_CREATED" in result.diagnostics


@pytest.mark.parametrize(
    ("http_status", "expected"),
    [(401, "HTTP_AUTH_ERROR"), (429, "HTTP_RATE_LIMIT"), (500, "HTTP_SERVER_ERROR")],
)
def test_http_failures_are_explicit_and_never_neutral(monkeypatch, http_status, expected) -> None:
    result = normalizer(monkeypatch, lambda *_: response("{}", http_status)).normalize(summary(), packet(), AS_OF)
    assert result.error_code == expected
    assert result.signal is None
    assert result.status is not GroundedResearchStatus.AVAILABLE


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("", "EMPTY_ASSISTANT_CONTENT"),
        ("not-json", "NON_JSON_MODEL_OUTPUT"),
        (json.dumps({"status": "AVAILABLE", "reason": "x", "direction": "BULLISH", "thesis": "x", "cited_evidence_ids": ["missing"]}), "SCHEMA_VALIDATION_FAILURE"),
        (json.dumps({"status": "AVAILABLE", "reason": "x", "direction": "BULLISH", "conviction": "0.4", "thesis": "x", "cited_evidence_ids": ["missing"]}), "CITATION_VALIDATION_FAILURE"),
        (json.dumps({"status": "ABSTAIN", "reason": "Insufficient certified grounding."}), "MODEL_ABSTAIN"),
    ],
)
def test_invalid_or_abstaining_content_fails_closed(monkeypatch, content, expected) -> None:
    result = normalizer(monkeypatch, lambda *_: response(content)).normalize(summary(), packet(), AS_OF)
    assert result.error_code == expected
    assert result.signal is None


def test_timeout_is_explicit(monkeypatch) -> None:
    def timeout(*_):
        raise TimeoutError()
    result = normalizer(monkeypatch, timeout).normalize(summary(), packet(), AS_OF)
    assert result.status is GroundedResearchStatus.TIMEOUT
    assert result.error_code == "TIMEOUT"


def test_provider_envelope_mismatch_is_explicit(monkeypatch) -> None:
    result = normalizer(monkeypatch, lambda *_: (200, b'{"unexpected": true}', {})).normalize(summary(), packet(), AS_OF)
    assert result.error_code == "PROVIDER_SCHEMA_MISMATCH"
    assert result.signal is None