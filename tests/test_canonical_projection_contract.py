"""Cross-artifact regressions: inspect real serialized files, not substrings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from meridian.application import MeridianApplicationService
from meridian.canonical_run import (
    CanonicalRunSnapshot,
    ExecutionState,
    IdempotencyState,
    assert_report_projection_consistency,
    canonical_snapshot,
    cli_summary,
    mapping,
    render_canonical_audit,
    seal_canonical_report,
)
from meridian.daily_closure import persist_run_report
from meridian.report_bundle import verify_report_bundle
from meridian.run_health import build_run_health
from meridian.runtime import RuntimePaths

SCENARIOS = (
    "first_no_action", "paper_fills", "provider_fallback", "research_executed",
    "research_fallback", "research_unavailable", "duplicate", "prior_canonical",
    "quote_blocked", "market_closed", "metadata_degraded", "hard_blocker",
)


def fixture(scenario: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "meridian-paper-daily.v1", "paper_run_id": "paper-daily-contract",
        "canonical_run_id": "daily-contract", "analysis_time": "2026-10-07T15:00:00+00:00",
        "trading_date": "2026-10-07", "status": "PAPER_NO_TRADE",
        "account": {"account": "Schwab-Paper", "cash": "100000.00", "positions": []},
        "performance": {"nav": "100000.00", "cash": "100000.00"},
        "market": {"status": "PASS", "session": "OPEN", "quote_certification": "BLOCKED",
            "provider_probes": {"AAPL": {
                "primary": {"provider": "yahoo", "status": "OK"},
                "secondary": {"provider": "nasdaq", "status": "OK"},
                "selected_provider": "yahoo", "selection": "PRIMARY"}}},
        "research": {"context": {"status": "AVAILABLE"}, "research_mode": "FULL_RESEARCH",
            "research_confidence": 0.71, "llm_available": True},
        "research_intelligence": {"research_state": "RESEARCH_READY", "confidence": {"system_confidence": 0.71},
            "stages": {"PRIMARY_ANALYST": {"status": "SUCCESS", "duration_ms": 4, "schema_valid": True}}},
        "decision": {"status": "NO_ACTION"}, "orders": [],
        "paper_execution": {"status": "PAPER_NO_TRADE", "authority": "PAPER_EXECUTION_ONLY", "intent_count": 0, "fills": []},
        "stages": [{"stage": "MARKET", "status": "PASS"}, {"stage": "RESEARCH", "status": "AVAILABLE"},
            {"stage": "DECISION", "status": "NO_ACTION"}, {"stage": "PAPER_EXECUTION", "status": "PAPER_NO_TRADE"}],
        "idempotency": {"state": "EXECUTED_THIS_RUN", "ledger_mutated_current_run": False,
            "orders_created_current_run": 0, "fills_created_current_run": 0},
        "broker_submission": "DISABLED", "quote_certification": "BLOCKED",
        "blockers": [], "next_actions": ["Review the canonical paper report; broker submission remains disabled."],
    }
    if scenario == "paper_fills":
        payload.update(status="PAPER_READY", decision={"status": "DRAFT"},
            paper_execution={"status": "PAPER_COMPLETE", "authority": "PAPER_EXECUTION_ONLY", "intent_count": 1,
                "fills": [{"ticker": "AAPL", "side": "BUY", "quantity": "10", "fill_price": "100", "fees": "0"}]},
            account={"account": "Schwab-Paper", "cash": "99000.00", "positions": [{"ticker": "AAPL", "quantity": "10"}]},
            performance={"nav": "100000.00", "cash": "99000.00"},
            idempotency={"state": "EXECUTED_THIS_RUN", "ledger_mutated_current_run": True, "orders_created_current_run": 1, "fills_created_current_run": 1})
    if scenario == "provider_fallback":
        probe = mapping(mapping(payload["market"])["provider_probes"])["AAPL"]
        assert isinstance(probe, dict)
        probe.update(primary={"provider": "yahoo", "status": "UNAVAILABLE"}, selected_provider="nasdaq", selection="FALLBACK")
    if scenario == "research_fallback":
        mapping(payload["research"]).update(research_mode="DEGRADED_RESEARCH", fallback_reason="NATIVE_PROVIDER_TIMEOUT", llm_available=False)
        mapping(payload["research_intelligence"])["research_state"] = "RESEARCH_DEGRADED"
    if scenario in {"research_unavailable", "hard_blocker"}:
        payload.update(status="PAPER_BLOCKED", research={"context": {"status": "UNAVAILABLE"}, "llm_available": False},
            research_intelligence=None, paper_execution={"status": "PAPER_BLOCKED", "intent_count": 0, "fills": []},
            blockers=["RESEARCH_UNAVAILABLE"] if scenario == "research_unavailable" else ["ACCOUNT_STALE"])
    if scenario == "market_closed":
        mapping(payload["market"]).update(status="MARKET_CLOSED", session="CLOSED")
        payload.update(status="PAPER_WAITING_FOR_MARKET", paper_execution={"status": "PAPER_WAITING_FOR_MARKET", "intent_count": 0, "fills": []}, blockers=["MARKET_CLOSED"])
    if scenario == "metadata_degraded":
        mapping(payload["market"])["metadata_status"] = "DEGRADED"
        payload["warnings"] = ["OPTIONAL_METADATA_UNAVAILABLE"]
    if scenario == "duplicate":
        payload.update(status="PAPER_ALREADY_EXECUTED", research={"status": "SKIPPED", "invoked_in_current_run": False},
            research_intelligence=None, decision={"status": "SKIPPED"},
            market={"status": "SKIPPED", "session": "NOT_RUN"},
            paper_execution={"status": "PAPER_ALREADY_EXECUTED", "intent_count": 0, "fills": []},
            idempotency={"status": "ALREADY_EXECUTED", "attempted_run_id": "daily-contract", "authoritative_existing_run_id": "daily-original",
                "ledger_mutated_current_run": False, "orders_created_current_run": 0, "fills_created_current_run": 0})
        payload["stages"] = [{"stage": name, "status": "SKIPPED", "invoked_in_current_run": False} for name in ("MARKET", "RESEARCH", "DECISION", "PAPER_EXECUTION")]
    if scenario == "prior_canonical":
        payload["idempotency"] = {"state": "REUSED_EXISTING_CANONICAL_RUN", "authoritative_existing_run_id": "daily-original"}
        payload["stages"] = [{"stage": name, "status": status, "execution_state": "REUSED", "stage_source": "CANONICAL_RUN", "source_run_id": "daily-original"} for name, status in (("MARKET", "PASS"), ("RESEARCH", "AVAILABLE"), ("DECISION", "NO_ACTION"))]
    if scenario not in {"duplicate", "prior_canonical"}:
        statuses = {"MARKET": mapping(payload["market"])["status"],
            "RESEARCH": mapping(mapping(payload["research"])["context"])["status"],
            "DECISION": mapping(payload["decision"])["status"],
            "PAPER_EXECUTION": mapping(payload["paper_execution"])["status"]}
        stages = payload["stages"]
        assert isinstance(stages, list)
        for stage in stages:
            stage["status"] = str(statuses[stage["stage"]])
            if stage["stage"] == "PAPER_EXECUTION" and scenario in {"hard_blocker", "research_unavailable", "market_closed"}:
                stage["execution_state"] = "BLOCKED"
    return payload


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_lossless_persisted_projections(tmp_path: Path, scenario: str) -> None:
    payload = fixture(scenario)
    outputs = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(payload)
    assert verify_report_bundle(Path(outputs["report_bundle_json"]))["run_id"] == "paper-daily-contract"
    canonical = json.loads(Path(outputs["paper_report_json"]).read_text(encoding="utf-8"))
    health = json.loads(Path(outputs["run_health_json"]).read_text(encoding="utf-8"))
    markdown = Path(outputs["paper_report_markdown"]).read_text(encoding="utf-8")
    cli = json.loads(json.dumps(payload))
    assert_report_projection_consistency(canonical, markdown, health, cli)
    snapshot = canonical_snapshot(canonical)
    assert CanonicalRunSnapshot.model_validate(cli_summary(cli)) == snapshot
    assert snapshot.account == "Schwab-Paper"
    assert snapshot.execution.broker_submission == "DISABLED"
    assert not snapshot.execution.broker_side_effects
    assert snapshot.market.quote_certification == "BLOCKED"
    assert snapshot.decision.result_status == ("DRAFT" if scenario == "paper_fills" else "SKIPPED" if scenario == "duplicate" else "NO_ACTION")
    assert snapshot.market.session == ("CLOSED" if scenario == "market_closed" else "NOT_RUN" if scenario == "duplicate" else "OPEN")
    assert snapshot.execution.fill_count == (1 if scenario == "paper_fills" else 0)
    if scenario == "provider_fallback":
        assert snapshot.market.providers_attempted == ("nasdaq", "yahoo")
        assert snapshot.market.providers_used == ("nasdaq",)
        assert snapshot.market.fallbacks_used == ("AAPL:nasdaq",)
    if scenario in {"first_no_action", "research_executed"}:
        assert snapshot.research.execution_state is ExecutionState.EXECUTED
        assert snapshot.research.result_status == "AVAILABLE"
        assert snapshot.research.confidence == 0.71
        assert snapshot.idempotency.state is IdempotencyState.EXECUTED_THIS_RUN
    if scenario == "paper_fills":
        assert snapshot.execution.order_count == snapshot.execution.fill_count == 1
        assert snapshot.position_count == 1 and snapshot.cash == "99000.00"
    if scenario == "duplicate":
        assert snapshot.idempotency.state is IdempotencyState.IDEMPOTENCY_BLOCKED_DUPLICATE
        assert snapshot.research.execution_state is ExecutionState.NOT_REACHED
    if scenario == "prior_canonical":
        assert snapshot.research.execution_state is ExecutionState.REUSED
        assert snapshot.idempotency.state is IdempotencyState.REUSED_EXISTING_CANONICAL_RUN


@pytest.mark.parametrize("confidence", [None, 0, 0.25])
def test_confidence_nullable_and_zero_semantics(tmp_path: Path, confidence: float | None) -> None:
    payload = fixture("research_executed")
    mapping(payload["research"]).update(research_confidence=confidence)
    mapping(mapping(payload["research_intelligence"])["confidence"])["system_confidence"] = confidence
    snapshot = seal_canonical_report(payload)
    assert snapshot.research.confidence == confidence
    assert mapping(build_run_health(payload)["research"])["research_confidence"] == confidence
    # Daily and paper serializers consume the same confidence source.
    payload["run_id"] = "daily-contract"
    paths = RuntimePaths(tmp_path)
    json_path, md_path = persist_run_report(payload, paths)
    assert_report_projection_consistency(json.loads(json_path.read_text(encoding="utf-8")),
        md_path.read_text(encoding="utf-8"), build_run_health(payload), payload)


def test_legacy_unknowns_do_not_invent_success_or_positions() -> None:
    snapshot = canonical_snapshot({"run_id": "legacy", "portfolio": {"positions": [{"ticker": "AAPL"}]}})
    assert snapshot.research.execution_state is ExecutionState.UNKNOWN
    assert snapshot.position_count is None
    assert snapshot.nav is None and snapshot.cash is None
    assert all(s["execution_state"] == "UNKNOWN" for s in build_run_health({"run_id": "legacy"})["stages"])  # type: ignore[union-attr]


def test_sealed_state_is_source_and_does_not_read_new_legacy_probes() -> None:
    payload = fixture("provider_fallback")
    expected = seal_canonical_report(payload)
    payload["research"] = {"status": "NOT_RUN"}
    payload["market"] = {}
    health = build_run_health(payload)
    assert canonical_snapshot(health) == expected
    assert mapping(health["research"])["status"] == "AVAILABLE"
    assert mapping(health["market_data"])["fallbacks_used"] == ["AAPL:nasdaq"]


@pytest.mark.parametrize("artifact", ["markdown", "health", "cli", "visible_markdown", "health_status"])
def test_contract_rejects_drift(artifact: str) -> None:
    payload = fixture("research_executed")
    snapshot = seal_canonical_report(payload)
    markdown = render_canonical_audit(snapshot)
    health = build_run_health(payload)
    cli = deepcopy(payload)
    if artifact == "markdown":
        markdown = markdown.replace('"trading_date": "2026-10-07"', '"trading_date": "2026-10-06"')
    elif artifact == "visible_markdown":
        markdown = markdown.replace("| Research result | AVAILABLE |", "| Research result | NOT_RUN |")
    elif artifact == "health_status":
        mapping(health["research"])["status"] = "NOT_RUN"
    else:
        mapping((health if artifact == "health" else cli)["canonical_state"])["cash"] = "0"
    with pytest.raises(AssertionError):
        assert_report_projection_consistency(payload, markdown, health, cli)


def test_fresh_process_reloads_persisted_truth(tmp_path: Path) -> None:
    outputs = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(fixture("provider_fallback"))
    script = """import json,sys
from pathlib import Path
from meridian.canonical_run import assert_report_projection_consistency
from meridian.report_bundle import verify_report_bundle
p,m,h = map(Path,sys.argv[1:])
canonical=json.loads(p.read_text(encoding='utf-8'))
assert verify_report_bundle(p.parent / 'report_bundle.json')['run_id'] == canonical['canonical_state']['run_id']
assert_report_projection_consistency(canonical,m.read_text(encoding='utf-8'),json.loads(h.read_text(encoding='utf-8')),canonical)
print('FRESH_PROCESS_CONSISTENCY_PASS')
"""
    environment = {**os.environ, "MERIDIAN_HOME": str(tmp_path), "MERIDIAN_CACHE": str(tmp_path / "cache")}
    completed = subprocess.run([sys.executable, "-c", script, outputs["paper_report_json"], outputs["paper_report_markdown"], outputs["run_health_json"]],
        capture_output=True, text=True, env=environment, check=True, timeout=20)
    assert completed.stdout.strip() == "FRESH_PROCESS_CONSISTENCY_PASS"


@pytest.mark.parametrize("mutation", ["broker", "certification", "duplicate_mutation"])
def test_impossible_authority_states_rejected(mutation: str) -> None:
    payload = fixture("duplicate" if mutation == "duplicate_mutation" else "research_executed")
    if mutation == "broker":
        payload["broker_submission"] = "ENABLED"
    elif mutation == "certification":
        payload["quote_certification"] = "CERTIFIED"
    else:
        mapping(payload["idempotency"])["ledger_mutated_current_run"] = True
    with pytest.raises(ValueError):
        canonical_snapshot(payload)


def test_bundle_rejects_tampered_artifact(tmp_path: Path) -> None:
    outputs = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(fixture("research_executed"))
    Path(outputs["run_health_json"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="REPORT_BUNDLE_HASH_MISMATCH"):
        verify_report_bundle(Path(outputs["report_bundle_json"]))


def test_partial_persistence_never_publishes_complete_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.write_text
    def reject_markdown(path: Path, *args, **kwargs):
        if path.name == "paper-daily.tmp" and path.with_suffix(".json").exists():
            raise PermissionError("injected markdown publication failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", reject_markdown)
    with pytest.raises(PermissionError):
        MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(fixture("first_no_action"))
    assert list(tmp_path.rglob("paper-daily.json"))
    assert not list(tmp_path.rglob("report_bundle.json"))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_fresh_cli_summary_matches_artifacts(tmp_path: Path, scenario: str) -> None:
    payload = fixture(scenario)
    outputs = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(payload)
    script = """import json,sys
from meridian.application import MeridianApplicationService
from meridian.application_cli import main
payload=json.load(open(sys.argv.pop(1),encoding='utf-8'))
MeridianApplicationService.paper_run=lambda self,*args,**kwargs: payload
raise SystemExit(main())
"""
    completed = subprocess.run([sys.executable, "-c", script, outputs["paper_report_json"], "paper", "run", "--json"],
        capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)
    assert completed.returncode == (2 if scenario in {"hard_blocker", "research_unavailable", "market_closed"} else 0), completed.stderr
    cli = json.loads(completed.stdout)
    canonical = json.loads(Path(outputs["paper_report_json"]).read_text(encoding="utf-8"))
    health = json.loads(Path(outputs["run_health_json"]).read_text(encoding="utf-8"))
    assert_report_projection_consistency(canonical, Path(outputs["paper_report_markdown"]).read_text(encoding="utf-8"), health, cli)


def test_published_schema_matches_typed_contract() -> None:
    root = Path(__file__).parents[1] / "schemas"
    assert json.loads((root / "meridian-canonical-run.v1.schema.json").read_text(encoding="utf-8")) == CanonicalRunSnapshot.model_json_schema()
    for schema in ("meridian-paper-daily.v1", "meridian-run-health.v1"):
        contract = json.loads((root / (schema + ".schema.json")).read_text(encoding="utf-8"))
        assert contract["properties"]["canonical_state"]["$ref"] == "meridian-canonical-run.v1.schema.json"
        assert "canonical_state" not in contract["required"]  # Old v1 receipts remain readable.


def test_latest_query_uses_final_paper_state_and_checks_publication(tmp_path: Path) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path))
    outputs = service._persist_paper_report(fixture("paper_fills"))
    latest = service.latest_report()
    assert latest["publication_status"] == "COMPLETE"
    summary = mapping(mapping(latest["report"])["canonical_summary"])
    assert summary["result_status"] == "PAPER_READY"
    assert mapping(summary["execution"])["fill_count"] == 1
    assert "fills" not in mapping(summary["execution"])
    Path(outputs["run_health_json"]).write_text("{}", encoding="utf-8")
    assert service.latest_report()["publication_status"] == "INVALID"


def test_serializers_restore_legacy_display_fields_from_sealed_truth(tmp_path: Path) -> None:
    payload = fixture("paper_fills")
    expected = seal_canonical_report(payload)
    payload.update(status="PAPER_BLOCKED", performance={"nav": "0", "cash": "0"},
        portfolio={"positions": []}, research={"status": "NOT_RUN"}, market={"status": "CLOSED"})
    outputs = MeridianApplicationService(RuntimePaths(tmp_path))._persist_paper_report(payload)
    restored = json.loads(Path(outputs["paper_report_json"]).read_text(encoding="utf-8"))
    assert canonical_snapshot(restored) == expected
    assert restored["performance"]["cash"] == "99000.00"
    assert restored["status"] == "PAPER_READY"
    assert restored["market"]["status"] == "PASS"
    assert len(restored["portfolio"]["positions"]) == 1
    markdown = Path(outputs["paper_report_markdown"]).read_text(encoding="utf-8")
    assert "NAV: **$100000.00**" in markdown
    assert "Cash: **$99000.00**" in markdown
    assert_report_projection_consistency(restored, markdown,
        json.loads(Path(outputs["run_health_json"]).read_text(encoding="utf-8")), payload)
