"""Versioned, authority-free reporting truth and lossless projections.

Only the compatibility boundary reads legacy dictionaries. Consumers use the
persisted snapshot; no provider, ledger or policy is consulted by projections.
"""

from __future__ import annotations

import json
from copy import deepcopy
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionState(StrEnum):
    UNKNOWN = "UNKNOWN"
    EXECUTED = "EXECUTED"
    INHERITED = "INHERITED"
    REUSED = "REUSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NOT_REACHED = "NOT_REACHED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IdempotencyState(StrEnum):
    EXECUTED_THIS_RUN = "EXECUTED_THIS_RUN"
    REUSED_EXISTING_CANONICAL_RUN = "REUSED_EXISTING_CANONICAL_RUN"
    IDEMPOTENCY_BLOCKED_DUPLICATE = "IDEMPOTENCY_BLOCKED_DUPLICATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_REACHED = "NOT_REACHED"
    FAILED = "FAILED"


class FrozenState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CanonicalStageResult(FrozenState):
    name: str
    execution_state: ExecutionState
    result_status: str
    source: Literal["CURRENT_RUN", "CANONICAL_RUN", "LEGACY_REPORT", "UNRECORDED"]
    source_run_id: str | None = None


class CanonicalResearchState(FrozenState):
    execution_state: ExecutionState
    result_status: str
    research_state: str | None = None
    mode: str | None = None
    confidence: float | str | None = None
    llm_available: bool | None = None
    fallback_reason: str | None = None
    intelligence: dict[str, object] = Field(default_factory=dict)
    details: dict[str, object] = Field(default_factory=dict)


class CanonicalMarketState(FrozenState):
    result_status: str
    session: str | None = None
    quote_certification: str
    provider_probes: dict[str, object] = Field(default_factory=dict)
    providers_attempted: tuple[str, ...] = ()
    providers_used: tuple[str, ...] = ()
    fallbacks_used: tuple[str, ...] = ()
    observations: dict[str, object] = Field(default_factory=dict)


class CanonicalDecisionState(FrozenState):
    result_status: str
    order_count: int | None = None
    orders: tuple[dict[str, object], ...] = ()
    context: dict[str, object] = Field(default_factory=dict)


class CanonicalExecutionState(FrozenState):
    execution_state: ExecutionState
    result_status: str
    order_count: int | None = None
    fill_count: int | None = None
    authority: str = "NONE"
    broker_submission: Literal["DISABLED"] = "DISABLED"
    broker_side_effects: Literal[False] = False
    fills: tuple[dict[str, object], ...] = ()


class CanonicalIdempotencyState(FrozenState):
    state: IdempotencyState
    attempted_run_id: str
    authoritative_existing_run_id: str | None = None
    ledger_mutated_current_run: bool | None = None
    orders_created_current_run: int | None = None
    fills_created_current_run: int | None = None


class CanonicalRunSnapshot(FrozenState):
    schema_version: Literal["meridian-canonical-run.v1"] = "meridian-canonical-run.v1"
    run_id: str
    canonical_run_id: str
    paper_run_id: str | None = None
    trading_date: str | None = None
    account: str | None = None
    result_status: str
    nav: str | None = None
    cash: str | None = None
    position_count: int | None = None
    positions: tuple[dict[str, object], ...] = ()
    market: CanonicalMarketState
    research: CanonicalResearchState
    decision: CanonicalDecisionState
    execution: CanonicalExecutionState
    idempotency: CanonicalIdempotencyState
    stages: tuple[CanonicalStageResult, ...] = ()
    blockers: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    status_dimensions: dict[str, object] = Field(default_factory=dict)
    readiness: dict[str, object] = Field(default_factory=dict)
    manual_authority: str | None = None
    forward_evidence: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coherent_identity_and_authority(self) -> CanonicalRunSnapshot:
        if self.paper_run_id and self.run_id != self.paper_run_id:
            raise ValueError("PAPER_REPORT_IDENTITY_MISMATCH")
        if self.market.quote_certification != "BLOCKED":
            raise ValueError("PUBLIC_QUOTE_CERTIFICATION_AUTHORITY_FORBIDDEN")
        if self.execution.order_count is not None and self.execution.order_count < 0:
            raise ValueError("NEGATIVE_ORDER_COUNT")
        if self.idempotency.state is IdempotencyState.IDEMPOTENCY_BLOCKED_DUPLICATE:
            if self.idempotency.ledger_mutated_current_run is True:
                raise ValueError("DUPLICATE_LEDGER_MUTATION")
            if self.idempotency.fills_created_current_run not in {None, 0}:
                raise ValueError("DUPLICATE_FILL_CREATION")
        return self


def mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def first(*values: object) -> object:
    """Null means missing; zero, false and empty containers remain real facts."""
    return next((value for value in values if value is not None), None)


def optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def sequence(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def display(value: object) -> str:
    return "NOT_AVAILABLE" if value is None else str(value)


def _execution(status: str, *, invoked: object = None) -> ExecutionState:
    if invoked is None and status in {"NOT_RECORDED", "UNKNOWN"}:
        return ExecutionState.UNKNOWN
    if invoked is False or status.startswith("NOT_RUN") or status in {"SKIPPED", "NOT_CONFIGURED", "NOT_RECORDED", "UNKNOWN"}:
        return ExecutionState.NOT_REACHED
    if status in {"INHERITED", "REUSED", "NOT_APPLICABLE", "NOT_REACHED"}:
        return ExecutionState(status)
    if status in {"FAILED", "ERROR", "TIMEOUT", "RATE_LIMITED", "AUTH_ERROR", "SCHEMA_ERROR", "PROCESS_ERROR"}:
        return ExecutionState.FAILED
    if status == "BLOCKED" or status.startswith("BLOCKED_"):
        return ExecutionState.BLOCKED
    return ExecutionState.EXECUTED


def snapshot_from_legacy(payload: dict[str, object]) -> CanonicalRunSnapshot:
    """Conservative v1 reader. Missing evidence never means success/inheritance."""
    paper_id = optional_text(payload.get("paper_run_id"))
    run_id = str(first(paper_id, payload.get("run_id"), "UNKNOWN"))
    canonical_id = str(first(payload.get("canonical_run_id"), payload.get("run_id"), run_id))
    research = mapping(payload.get("research"))
    context = mapping(research.get("context"))
    decision_context = mapping(payload.get("decision_context"))
    intelligence = mapping(payload.get("research_intelligence"))
    confidence = mapping(intelligence.get("confidence"))
    structured = mapping(research.get("structured_response"))
    market = mapping(payload.get("market"))
    paper = mapping(payload.get("paper_execution"))
    if payload.get("broker_submission", "DISABLED") != "DISABLED":
        raise ValueError("BROKER_AUTHORITY_FORBIDDEN")
    decision = mapping(payload.get("decision"))
    account = mapping(payload.get("account"))
    portfolio = mapping(payload.get("portfolio"))
    performance = mapping(payload.get("performance"))
    idem = mapping(payload.get("idempotency"))
    duplicate = payload.get("status") == "PAPER_ALREADY_EXECUTED"
    stages: list[CanonicalStageResult] = []
    raw_stages = payload.get("stages")
    if isinstance(raw_stages, list):
        for item in raw_stages:
            item = mapping(item)
            name = str(item.get("stage", "")).upper()
            if not name:
                continue
            status = str(first(item.get("result_status"), item.get("status"), "UNKNOWN"))
            state = _execution(status, invoked=item.get("invoked_in_current_run"))
            if item.get("execution_state") is not None:
                state = ExecutionState(str(item["execution_state"]))
            source = "CANONICAL_RUN" if item.get("stage_source") == "CANONICAL_RUN" else "CURRENT_RUN"
            stages.append(CanonicalStageResult(name=name, execution_state=state,
                result_status=status, source=source, source_run_id=optional_text(item.get("source_run_id"))))
    research_status = str(first(payload.get("research_status"), context.get("status"),
        research.get("status"), decision_context.get("research_status"), "UNKNOWN"))
    research_stage = next((s for s in stages if s.name == "RESEARCH"), None)
    research_execution = research_stage.execution_state if research_stage else _execution(research_status, invoked=research.get("invoked_in_current_run"))
    for name, raw in mapping(intelligence.get("stages")).items():
        if not any(s.name == name for s in stages):
            native = mapping(raw)
            status = str(native.get("status", "UNKNOWN"))
            stages.append(CanonicalStageResult(name=name, execution_state=_execution(status),
                result_status=status, source="CANONICAL_RUN" if paper_id else "CURRENT_RUN",
                source_run_id=canonical_id))
    probes = deepcopy(mapping(first(payload.get("provider_probes"), market.get("provider_probes"))))
    attempted: set[str] = set()
    used: set[str] = set()
    fallbacks: set[str] = set()
    for symbol, raw_probe in probes.items():
        probe = mapping(raw_probe)
        for lane in ("primary", "secondary", "history"):
            result = mapping(probe.get(lane))
            provider = first(result.get("requested_provider"), result.get("provider"))
            if provider and result.get("status") not in {None, "NOT_RUN", "SKIPPED", "NOT_REACHED"}:
                attempted.add(str(provider))
        selected = first(probe.get("selected_provider"), mapping(probe.get("selected")).get("provider"))
        if selected:
            used.add(str(selected))
            if probe.get("selection") in {"secondary", "SECONDARY", "FALLBACK"}:
                fallbacks.add(f"{symbol}:{selected}")
        history = mapping(probe.get("history"))
        if history.get("status") == "PASS" and history.get("provider"):
            used.add(str(history["provider"]))
    execution_status = str(first(paper.get("status"), "NOT_APPLICABLE"))
    fill_list = first(paper.get("fills"), payload.get("fills"))
    fill_count = len(fill_list) if isinstance(fill_list, list) else None
    intent_count = paper.get("intent_count")
    order_list = payload.get("orders")
    decision_count = len(order_list) if isinstance(order_list, list) else None
    idem_state = IdempotencyState.NOT_APPLICABLE
    if duplicate:
        idem_state = IdempotencyState.IDEMPOTENCY_BLOCKED_DUPLICATE
    elif idem.get("state") is not None:
        idem_state = IdempotencyState(str(idem["state"]))
    elif stages:
        idem_state = IdempotencyState.EXECUTED_THIS_RUN if any(s.execution_state == ExecutionState.EXECUTED for s in stages) else IdempotencyState.NOT_REACHED
    elif paper_id:
        idem_state = IdempotencyState.NOT_REACHED
    positions = account.get("positions") if paper_id else payload.get("current_holdings")
    # A target portfolio is never mistaken for actual positions.
    raw_confidence = first(confidence.get("system_confidence"), research.get("research_confidence"), structured.get("confidence"))
    return CanonicalRunSnapshot(
        run_id=run_id, canonical_run_id=canonical_id, paper_run_id=paper_id,
        trading_date=optional_text(payload.get("trading_date")),
        account=optional_text(first(account.get("account"), payload.get("account") if isinstance(payload.get("account"), str) else None)),
        result_status=str(payload.get("status", "UNKNOWN")),
        nav=optional_text(performance.get("nav")),
        cash=optional_text(first(performance.get("cash"), account.get("cash"), portfolio.get("cash") if paper_id else None)),
        position_count=len(positions) if isinstance(positions, list) else None,
        positions=tuple(deepcopy(mapping(x)) for x in sequence(positions)),
        market=CanonicalMarketState(result_status=str(first(payload.get("data_status"), market.get("status"), "UNKNOWN")),
            session=optional_text(first(market.get("session"), mapping(mapping(payload.get("startup_diagnostics")).get("market_status")).get("status"))),
            quote_certification=str(first(payload.get("quote_certification"), market.get("quote_certification"), "BLOCKED")),
            provider_probes=probes, providers_attempted=tuple(sorted(attempted)), providers_used=tuple(sorted(used)), fallbacks_used=tuple(sorted(fallbacks)),
            observations=deepcopy(mapping(first(payload.get("market_observations"), market.get("observations"))))),
        research=CanonicalResearchState(execution_state=research_execution, result_status=research_status,
            research_state=optional_text(intelligence.get("research_state")), mode=optional_text(research.get("research_mode")),
            confidence=raw_confidence if isinstance(raw_confidence, (float, int, str)) else None,
            llm_available=optional_bool(research.get("llm_available")),
            fallback_reason=optional_text(research.get("fallback_reason")), intelligence=deepcopy(intelligence), details=deepcopy(research)),
        decision=CanonicalDecisionState(result_status=str(first(decision.get("status"), payload.get("status"), "UNKNOWN")), order_count=decision_count,
            orders=tuple(deepcopy(mapping(x)) for x in sequence(order_list)), context=deepcopy(mapping(first(decision.get("context"), payload.get("decision_context"))))),
        execution=CanonicalExecutionState(execution_state=ExecutionState.NOT_APPLICABLE if not paper_id else ExecutionState.BLOCKED if duplicate or execution_status in {"PAPER_BLOCKED", "PAPER_WAITING_FOR_MARKET"} else _execution(execution_status),
            result_status=execution_status, order_count=int(intent_count) if isinstance(intent_count, (int, str)) else None,
            fill_count=fill_count, authority=str(first(paper.get("authority"), "NONE")), fills=tuple(deepcopy(mapping(x)) for x in sequence(fill_list))),
        idempotency=CanonicalIdempotencyState(state=idem_state,
            attempted_run_id=str(first(idem.get("attempted_run_id"), canonical_id)),
            authoritative_existing_run_id=optional_text(idem.get("authoritative_existing_run_id")),
            ledger_mutated_current_run=optional_bool(idem.get("ledger_mutated_current_run")),
            orders_created_current_run=optional_int(idem.get("orders_created_current_run")),
            fills_created_current_run=optional_int(idem.get("fills_created_current_run"))),
        stages=tuple(stages), blockers=tuple(str(x) for x in sequence(payload.get("blockers", payload.get("blocked_reasons"))) if isinstance(x, str)),
        next_actions=tuple(str(x) for x in sequence(payload.get("next_actions")) if isinstance(x, str)),
        status_dimensions=deepcopy(mapping(payload.get("status_dimensions"))),
        readiness=deepcopy(mapping(payload.get("readiness"))),
        forward_evidence=deepcopy(mapping(payload.get("forward_evidence"))),
        manual_authority=optional_text(first(mapping(payload.get("manual_authority")).get("status"),
            payload.get("manual_authority") if isinstance(payload.get("manual_authority"), str) else None)),
    )


def canonical_snapshot(payload: dict[str, object]) -> CanonicalRunSnapshot:
    persisted = payload.get("canonical_state")
    if isinstance(persisted, dict) and "forward_evidence" not in persisted:
        # Pre-extension snapshots kept this recorded fact in the enclosing
        # report. Import it once; an explicitly sealed empty value stays empty.
        persisted = {**persisted, "forward_evidence": deepcopy(mapping(payload.get("forward_evidence")))}
    return CanonicalRunSnapshot.model_validate(persisted) if persisted is not None else snapshot_from_legacy(payload)


def seal_canonical_report(payload: dict[str, object]) -> CanonicalRunSnapshot:
    snapshot = canonical_snapshot(payload)
    # Legacy presentation fields are serializers of the sealed truth, too.
    # Auxiliary analytics stay as recorded; they never replace these facts.
    payload.update({"status": snapshot.result_status, "research_status": snapshot.research.result_status,
        "forward_evidence": deepcopy(snapshot.forward_evidence),
        "research": deepcopy(snapshot.research.details),
        "research_intelligence": deepcopy(snapshot.research.intelligence) or None})
    if snapshot.idempotency.state is not IdempotencyState.NOT_APPLICABLE:
        payload["idempotency"] = {**mapping(payload.get("idempotency")), **snapshot.idempotency.model_dump(mode="json")}
    facts = {stage.name: stage for stage in snapshot.stages}
    for item in sequence(payload.get("stages")):
        if isinstance(item, dict) and (fact := facts.get(str(item.get("stage", "")).upper())):
            item.update({"status": fact.result_status, "result_status": fact.result_status,
                "execution_state": fact.execution_state.value, "stage_source": fact.source, "source_run_id": fact.source_run_id})
    if snapshot.paper_run_id:
        market = mapping(payload.get("market"))
        payload["market"] = {**market, "status": snapshot.market.result_status,
            "session": snapshot.market.session, "provider_probes": deepcopy(snapshot.market.provider_probes),
            "observations": deepcopy(snapshot.market.observations), "quote_certification": snapshot.market.quote_certification}
        decision = mapping(payload.get("decision"))
        payload["decision"] = {**decision, "status": snapshot.decision.result_status, "context": deepcopy(snapshot.decision.context)}
        portfolio = mapping(payload.get("portfolio"))
        payload["portfolio"] = {**portfolio, "cash": snapshot.cash, "positions": list(snapshot.positions)}
        performance = mapping(payload.get("performance"))
        payload["performance"] = {**performance, "nav": snapshot.nav, "cash": snapshot.cash}
        execution = mapping(payload.get("paper_execution"))
        payload["paper_execution"] = {**execution, "status": snapshot.execution.result_status,
            "intent_count": snapshot.execution.order_count, "fills": list(snapshot.execution.fills)}
    payload["canonical_state"] = snapshot.model_dump(mode="json")
    return snapshot


def cli_summary(payload: dict[str, object]) -> dict[str, object]:
    """CLI/API consumers receive the same business state, without recomputation."""
    return canonical_snapshot(payload).model_dump(mode="json")


def render_canonical_audit(snapshot: CanonicalRunSnapshot) -> str:
    """Human audit and structured, lossless receipt share the same typed source."""
    fields = {
        "Run ID": snapshot.run_id, "Canonical run ID": snapshot.canonical_run_id,
        "Trading date": snapshot.trading_date, "Account": snapshot.account,
        "Result": snapshot.result_status, "NAV": snapshot.nav, "Cash": snapshot.cash,
        "Position count": snapshot.position_count, "Market result": snapshot.market.result_status,
        "Research execution": snapshot.research.execution_state, "Research result": snapshot.research.result_status,
        "Research confidence": snapshot.research.confidence, "Research fallback": snapshot.research.fallback_reason,
        "Decision": snapshot.decision.result_status, "Decision order count": snapshot.decision.order_count,
        "Paper result": snapshot.execution.result_status, "Paper intent count": snapshot.execution.order_count,
        "Fill count": snapshot.execution.fill_count, "Quote certification": snapshot.market.quote_certification,
        "Broker submission": snapshot.execution.broker_submission, "Broker side effects": snapshot.execution.broker_side_effects,
        "Idempotency": snapshot.idempotency.state,
        "Providers attempted": ", ".join(snapshot.market.providers_attempted),
        "Providers used": ", ".join(snapshot.market.providers_used),
        "Provider fallbacks": ", ".join(snapshot.market.fallbacks_used),
    }
    lines = ["## Canonical audit", "", "| Fact | Value |", "| --- | --- |"]
    lines.extend(f"| {key} | {display(value)} |" for key, value in fields.items())
    summaries: list[str] = []
    for symbol, probe in sorted(snapshot.market.provider_probes.items()):
        observation = mapping(probe)
        states = mapping(observation.get("provider_health"))
        if states:
            summaries.append(f"{symbol}: {observation.get('selection', 'UNKNOWN')}; " + ", ".join(f"{provider} {mapping(state).get('status', 'UNKNOWN')}" for provider, state in sorted(states.items())))
    if summaries:
        lines.extend(["", "Provider health (observational; routing authority unchanged):", *[f"- {item}" for item in summaries]])
    confidence = mapping(snapshot.research.intelligence.get("confidence"))
    if confidence.get("composer_version"):
        lines.extend(["", f"Confidence source: {confidence['composer_version']}; deterministic evidence components; advisory authority only."])
    shared_ids = {mapping(mapping(stage).get("diagnostic")).get("shared_invocation_id") for stage in mapping(snapshot.research.intelligence.get("stages")).values() if mapping(mapping(stage).get("diagnostic")).get("shared_invocation")}
    if shared_ids:
        lines.extend(["", f"Research used {len(shared_ids)} shared invocation(s); role participation is logical and role durations are non-additive."])
    if snapshot.forward_evidence:
        forward = mapping(snapshot.forward_evidence.get("summary"))
        lines.extend(["", f"Forward evidence: {forward.get('evaluation_readiness', snapshot.forward_evidence.get('status', 'UNKNOWN'))}; verified samples {forward.get('sample_count', 'UNKNOWN')}; SHADOW_EVIDENCE_ONLY / NO_AUTOMATIC_PROMOTION."])
    lines.extend(["", "| Stage | Execution | Result | Source |", "| --- | --- | --- | --- |"])
    lines.extend(f"| {s.name} | {s.execution_state} | {s.result_status} | {s.source} ({display(s.source_run_id)}) |" for s in snapshot.stages)
    lines.extend(["", "Advisory research has no order, fill, position or broker authority.", "",
        "<details><summary>Lossless canonical state</summary>", "", "```meridian-canonical-state",
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False), "```", "", "</details>", ""])
    return "\n".join(lines)


def markdown_snapshot(markdown: str) -> CanonicalRunSnapshot:
    data = markdown.split("```meridian-canonical-state\n", 1)[1].split("\n```", 1)[0]
    return CanonicalRunSnapshot.model_validate_json(data)


def assert_report_projection_consistency(canonical: dict[str, object], markdown: str,
        health: dict[str, object], cli: dict[str, object]) -> None:
    expected = canonical_snapshot(canonical)
    if not (markdown_snapshot(markdown) == expected):
        raise AssertionError("MARKDOWN_CANONICAL_DRIFT")
    if render_canonical_audit(expected) not in markdown:
        raise AssertionError("MARKDOWN_DISPLAY_DRIFT")
    if not (canonical_snapshot(health) == expected):
        raise AssertionError("HEALTH_CANONICAL_DRIFT")
    if not (canonical_snapshot(cli) == expected):
        raise AssertionError("CLI_CANONICAL_DRIFT")
    if "summary" in cli:
        if not (CanonicalRunSnapshot.model_validate(cli["summary"]) == expected):
            raise AssertionError("CLI_SUMMARY_DRIFT")
    if not (cli["status"] == expected.result_status):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["run_id"] == expected.run_id):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["research"])["status"] == expected.research.result_status):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["research"])["execution_state"] == expected.research.execution_state):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    for key in ("providers_attempted", "providers_used", "fallbacks_used"):
        if not (mapping(health["market_data"])[key] == list(getattr(expected.market, key))):
            raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["market_data"])["status"] == expected.market.result_status):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["market_data"])["symbols"] == expected.market.provider_probes):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["decision"])["status"] == expected.decision.result_status):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["paper_execution"])["status"] == expected.execution.result_status):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["trading_date"] == expected.trading_date):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["account"] == expected.account):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["portfolio"] == {"nav": expected.nav, "cash": expected.cash, "position_count": expected.position_count}):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["decision"])["orders_created"] == expected.decision.order_count):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["paper_execution"])["intent_count"] == expected.execution.order_count):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["paper_execution"])["orders_executed"] == expected.execution.fill_count):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["broker_submission"] == expected.execution.broker_submission):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["broker_side_effects"] == expected.execution.broker_side_effects):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (mapping(health["market_data"])["quote_certification"] == expected.market.quote_certification):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["idempotency_state"] == expected.idempotency.model_dump(mode="json")):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["status_dimensions"] == expected.status_dimensions):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if not (health["readiness"] == expected.readiness):
        raise AssertionError("REPORT_PROJECTION_DRIFT")
    if health.get("forward_evidence") != expected.forward_evidence:
        raise AssertionError("FORWARD_EVIDENCE_PROJECTION_DRIFT")
    if not (health["manual_authority"] == expected.manual_authority):
        raise AssertionError("REPORT_PROJECTION_DRIFT")

def schema_json() -> str:
    return json.dumps(CanonicalRunSnapshot.model_json_schema(), indent=2) + "\n"
