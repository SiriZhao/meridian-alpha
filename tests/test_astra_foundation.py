from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.astra_research import (
    ClaimKind,
    MeridianResearchResult,
    ResearchClaim,
    ResearchEvidence,
    ResearchIntent,
    persist_research_result,
)
from meridian.mcp_server import (
    account_snapshot,
    mcp,
    registered_tool_names,
    runtime_status,
    validate_account_snapshot,
)
from meridian.runtime import RuntimePaths

NOW = datetime(2026, 9, 11, 16, tzinfo=UTC)


def evidence() -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id="ev-sec-1",
        source="https://www.sec.gov/example",
        observed_at=NOW - timedelta(days=1),
        known_at=NOW - timedelta(hours=1),
        analysis_cutoff=NOW,
        freshness="CURRENT_FILING",
        data_quality="HIGH",
        provenance="SEC accession fixture",
    )


def test_astra_fact_requires_known_evidence() -> None:
    item = evidence()
    result = MeridianResearchResult(
        subject="NVDA",
        analysis_cutoff=NOW,
        research_question="What is supported by current evidence?",
        intent=ResearchIntent.COMPANY_RESEARCH,
        facts=(ResearchClaim(kind=ClaimKind.FACT, statement="A filing exists.", evidence_ids=(item.evidence_id,)),),
        evidence=(item,),
        unknowns=("Current executable quote is unknown.",),
        confidence=Decimal("0.6"),
        evidence_coverage=Decimal("0.5"),
    )
    assert result.audit_metadata.execution_authority == "NONE"


def test_astra_rejects_unsupported_fact_and_future_evidence() -> None:
    with pytest.raises(ValueError, match="FACT_REQUIRES_EVIDENCE"):
        ResearchClaim(kind=ClaimKind.FACT, statement="Unsupported claim")
    with pytest.raises(ValueError, match="RESEARCH_EVIDENCE_AFTER_CUTOFF"):
        ResearchEvidence(
            evidence_id="future", source="source", observed_at=NOW,
            known_at=NOW + timedelta(seconds=1), analysis_cutoff=NOW,
            freshness="FUTURE", data_quality="REJECTED", provenance="fixture",
        )


def test_astra_contradictions_and_unknowns_are_explicit() -> None:
    left = evidence()
    right = left.model_copy(update={"evidence_id": "ev-sec-2", "provenance": "second source"})
    result = MeridianResearchResult(
        subject="NVDA", analysis_cutoff=NOW, research_question="Premortem",
        intent=ResearchIntent.PRE_MORTEM, contradicting_evidence=(left, right),
        unknowns=("The contradiction is unresolved.",), recommendation="NO_ACTION",
    )
    assert result.contradicting_evidence and result.unknowns


def test_astra_mcp_registration_and_no_broker_execution_surface() -> None:
    expected = {
        "runtime_status", "market_snapshot", "account_snapshot", "company_facts",
        "research_packet", "quant_metrics", "portfolio_context", "risk_analysis",
        "forward_evidence", "daily_closure", "audit_lookup",
    }
    names = registered_tool_names()
    assert expected <= names
    assert not any(token in name for name in names for token in ("submit", "cancel_order", "broker_login"))


def test_astra_mcp_tools_have_structured_read_only_schemas() -> None:
    tools = asyncio.run(mcp.list_tools())
    selected = [item for item in tools if item.name in registered_tool_names()]
    assert selected
    assert all(item.outputSchema for item in selected)
    assert all(item.annotations and item.annotations.readOnlyHint for item in selected)


def test_skill_is_astra_evidence_first() -> None:
    skill = Path("skills/meridian-alpha/SKILL.md").read_text(encoding="utf-8")
    for marker in ("FACT", "INFERENCE", "FORECAST", "UNKNOWN", "analysis cutoff"):
        assert marker in skill
    assert "never submits broker orders" in skill


def test_production_runtime_paths_do_not_write_project_tree(tmp_path: Path) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path / "runtime")})
    paths.ensure_directories()
    payload = paths.as_dict()
    assert Path(payload["home"]) == tmp_path / "runtime"
    assert "runs" in paths.directories() and "audit" in paths.directories()


def test_account_tool_rejects_future_snapshot() -> None:
    from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState

    account = AccountSnapshot(
        snapshot_id="future",
        account_alias="sanitized",
        provider="fixture",
        as_of=NOW + timedelta(seconds=1),
        total_equity=Decimal("100"),
        cash=Decimal("100"),
        sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )
    result = account_snapshot(account, NOW)
    assert result["valid"] is False
    assert result["errors"] == ["ACCOUNT_AFTER_CUTOFF"]


def test_account_tool_rejects_stale_snapshot() -> None:
    from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState

    account = AccountSnapshot(
        snapshot_id="stale",
        account_alias="sanitized",
        provider="fixture",
        as_of=NOW - timedelta(days=1),
        total_equity=Decimal("100"),
        cash=Decimal("100"),
        sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.STALE,
    )
    result = account_snapshot(account, NOW)
    assert result["valid"] is False
    assert result["errors"] == ["ACCOUNT_SNAPSHOT_STALE"]


def test_astra_eval_fixture_covers_required_behaviors() -> None:
    payload = json.loads(
        Path("evals/astra-research-fixtures.json").read_text(encoding="utf-8")
    )
    identifiers = {item["id"] for item in payload["fixtures"]}
    assert identifiers == {
        "unsupported-claim",
        "evidence-attribution",
        "contradiction-discovery",
        "uncertainty-reporting",
        "tool-selection",
        "research-completeness",
        "bull-with-material-contradiction",
        "cheap-with-deteriorating-fundamentals",
        "excellent-but-expensive",
        "earnings-beat-weak-guidance",
        "negative-headline-no-thesis-impact",
        "material-regulatory-risk",
        "insufficient-data",
        "future-information-contamination",
    }


def test_astra_research_audit_is_immutable_under_runtime_paths(tmp_path: Path) -> None:
    item = evidence()
    result = MeridianResearchResult(
        subject="NVDA",
        analysis_cutoff=NOW,
        research_question="Audit persistence",
        intent=ResearchIntent.COMPANY_RESEARCH,
        facts=(
            ResearchClaim(
                kind=ClaimKind.FACT,
                statement="A filing exists.",
                evidence_ids=(item.evidence_id,),
            ),
        ),
        evidence=(item,),
    )
    paths = RuntimePaths(tmp_path / "runtime")
    first = persist_research_result(result, paths)
    second = persist_research_result(result, paths)
    assert first == second
    assert first.parent == paths.audit / "research-results"
    assert first.read_text(encoding="utf-8") == result.stable_json() + "\n"


def test_legacy_account_validator_rejects_stale_snapshot_without_authority() -> None:
    from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState

    account = AccountSnapshot(
        snapshot_id="stale-validator", account_alias="sanitized", provider="fixture",
        as_of=NOW - timedelta(days=1), total_equity=Decimal("100"), cash=Decimal("100"),
        sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.STALE,
    )
    result = validate_account_snapshot(account)
    assert result["valid"] is False
    assert result["errors"] == ["ACCOUNT_SNAPSHOT_STALE"]
    assert result["execution_authority"] == "NONE"


def test_runtime_status_is_non_mutating_in_read_only_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("meridian.mcp_server.report", lambda *args, **kwargs: {
        "status": "PASS", "cache": {"status": "NOT_PROBED_READ_ONLY_HOST"}
    })
    result = runtime_status()
    assert result["status"] == "PASS"
    assert result["cache"]["status"] == "NOT_PROBED_READ_ONLY_HOST"
    assert result["execution_authority"] == "NONE"
