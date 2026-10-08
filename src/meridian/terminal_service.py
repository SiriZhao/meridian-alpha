"""Bounded in-memory research planning and evidence-first terminal presentation."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable
from decimal import Decimal
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.research_terminal import (
    PortfolioWhatIfRequest,
    PortfolioWhatIfResult,
    QuantModelRow,
    QuantModelView,
    QuantTerminalRequest,
    QuantTerminalSnapshot,
    challenger_policy,
    fingerprint,
    portfolio_what_if,
    quant_terminal_snapshot,
    risk_policy_fingerprint,
)
from meridian.schemas import StableModel

if TYPE_CHECKING:
    from meridian.config import ResearchSettings
    from meridian.daily_research import DailyResearchInput
    from meridian.gpt_native_research import NativeResearchResult, ResearchModelRuntime


class TerminalBudget(StableModel):
    version: Literal["terminal-budget.v1"] = "terminal-budget.v1"
    max_calculations: int = Field(default=2, ge=1, le=2)
    deadline_seconds: int = Field(default=30, ge=1, le=60)
    max_input_bytes: int = Field(default=2000000, ge=1000, le=2000000)
    cache_ttl_seconds: int = Field(default=60, ge=1, le=300)
    max_model_input_tokens: int = Field(default=32000, ge=1000, le=32000)


class TerminalTelemetry(StableModel):
    quant_ms: float = Field(ge=0)
    report_ms: float = Field(ge=0)
    risk_ms: float = Field(ge=0)
    cache_hit: bool
    calculations: int = Field(ge=0, le=2)
    provider_requests: Literal[0] = 0
    model_calls: Literal[0] = 0
    token_usage: None = None
    cost: None = None
    latency_accounting: Literal["WALL_CLOCK_COMPONENTS_NOT_SHARED_MODEL_STAGE_SUM"] = "WALL_CLOCK_COMPONENTS_NOT_SHARED_MODEL_STAGE_SUM"


class TerminalBrief(StableModel):
    schema_version: Literal["meridian-research-terminal.v1"] = "meridian-research-terminal.v1"
    status: Literal["RESEARCH_ONLY", "DEGRADED", "BLOCKED"]
    quant: QuantTerminalSnapshot
    portfolio: PortfolioWhatIfResult | None
    views: dict[str, Any]
    telemetry: TerminalTelemetry
    evidence_hash: str
    reasons: tuple[str, ...]
    execution_authority: Literal["NONE"] = "NONE"
    broker_submission: Literal["DISABLED"] = "DISABLED"


class TerminalPlanner:
    """Fixed allowlist, no recursive/model-authored dispatch and no disk cache.

    Only pure quant computations are memoized. Account/model conclusions never
    enter the cache. A changed cutoff, history, policy or engine misses the cache.
    The deadline is checked at computation boundaries; bounded local kernels
    cannot be cancelled midway and are never mistaken for bounded network calls.
    """
    allowed_actions = frozenset({"quant_research_snapshot", "portfolio_what_if"})

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self._cache: OrderedDict[str, tuple[float, QuantTerminalSnapshot]] = OrderedDict()

    def build(self, request: QuantTerminalRequest, *, portfolio: PortfolioWhatIfRequest | None = None,
              budget: TerminalBudget | None = None) -> TerminalBrief:
        budget = budget or TerminalBudget()
        start = self.clock()
        if len(request.stable_json().encode()) > budget.max_input_bytes:
            raise ValueError("TERMINAL_INPUT_BYTE_BUDGET_EXCEEDED")
        if portfolio and portfolio.analysis_cutoff != request.analysis_cutoff:
            raise ValueError("TERMINAL_SHARED_CUTOFF_REQUIRED")
        if portfolio and budget.max_calculations < 2:
            raise ValueError("TERMINAL_CALCULATION_BUDGET_EXCEEDED")
        quant_policy_hash, hard_risk_hash = challenger_policy().digest, risk_policy_fingerprint()
        key = fingerprint(request) + quant_policy_hash + hard_risk_hash + ENGINE_SOURCE_HASH
        cached = self._cache.get(key)
        hit = cached is not None and 0 <= start - cached[0] <= budget.cache_ttl_seconds
        snapshot = cached[1] if hit and cached else quant_terminal_snapshot(request)
        if (snapshot.policy_hash, snapshot.risk_policy_hash) != (quant_policy_hash, hard_risk_hash):
            raise ValueError("TERMINAL_POLICY_CHANGED_DURING_CALCULATION")
        end_quant = self.clock()
        if end_quant - start > budget.deadline_seconds:
            raise ValueError("TERMINAL_DEADLINE_EXCEEDED_QUANT")
        if not hit:
            self._cache[key] = (end_quant, snapshot)
            if len(self._cache) > 32:
                self._cache.popitem(last=False)
        hypothetical = portfolio_what_if(portfolio) if portfolio else None
        end_risk = self.clock()
        if end_risk - start > budget.deadline_seconds:
            raise ValueError("TERMINAL_DEADLINE_EXCEEDED_RISK")
        packet = snapshot.packet
        unknowns = list(packet.important_unknowns if packet else snapshot.reasons)
        views: dict[str, Any] = {
            "MARKET_OVERVIEW": {"analysis_cutoff": request.analysis_cutoff.isoformat(),
                "regime": packet.regime.model_dump(mode="json") if packet else None,
                "current_price": None, "unknowns": ["NO_CURRENT_QUOTE_SUPPLIED", "BREADTH_UNKNOWN"]},
            "QUANT_EXPLORER": {"engine": "V2.2_SHADOW", "rows": [r.model_dump(mode="json") for r in snapshot.rows],
                "packet": packet.model_dump(mode="json") if packet else None},
            "PORTFOLIO_RISK": hypothetical.model_dump(mode="json") if hypothetical else {"status": "BLOCKED", "reason": "AUTHORIZED_PAPER_SNAPSHOT_REQUIRED"},
            "RESEARCH_WORKSPACE": {"status": "NOT_RUN", "gpt_interpretation": None,
                "unknowns": unknowns, "reason": "DETERMINISTIC_EVIDENCE_AVAILABLE_WITHOUT_MODEL"},
            "DECISION_CONSOLE": [{"symbol": r.symbol, "category": "WAIT_FOR_EVIDENCE" if not r.eligible else "HOLD",
                "possible_manual_action": None, "entry_zone": None,
                "wait_reason": "FRESH_ACCOUNT_AND_EXECUTION_QUOTES_REQUIRE_INDEPENDENT_REVIEW",
                "evidence_ids": [r.evidence_id], "explanation_zh": r.chinese_explanation} for r in snapshot.rows],
            "EXPERIMENT_LABORATORY": {"status": "REAL_FINANCIAL_VALIDATION_PENDING", "alpha": "ALPHA_NOT_YET_DEMONSTRATED",
                "synthetic_output_is_financial_evidence": False, "registry_command": "meridian quant inspect --dataset <sealed-dataset.json>"},
            "OPERATIONAL_HEALTH": {"provider_status": "NOT_PROBED", "model_status": "NOT_RUN", "paper_status": "NOT_RUN",
                "broker_submission": "DISABLED", "canonical_strategy": "QUANT_V1_BASELINE"},
        }
        end = self.clock()
        if end - start > budget.deadline_seconds:
            raise ValueError("TERMINAL_DEADLINE_EXCEEDED_REPORT")
        seal = hashlib.sha256(json.dumps(views, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        return TerminalBrief(status="BLOCKED" if snapshot.status == "BLOCKED" else "DEGRADED" if hypothetical is None or hypothetical.status == "BLOCKED" else "RESEARCH_ONLY",
            quant=snapshot, portfolio=hypothetical, views=views, telemetry=TerminalTelemetry(
                quant_ms=max(0, (end_quant - start) * 1000), report_ms=max(0, (end - end_risk) * 1000),
                risk_ms=max(0, (end_risk - end_quant) * 1000),
                cache_hit=hit, calculations=(0 if hit else 1) + (1 if portfolio else 0)),
            evidence_hash=seal, reasons=snapshot.reasons)


def render_terminal(brief: TerminalBrief) -> str:
    """Concise Chinese terminal; structured JSON retains complete attribution."""
    lines = ["Meridian 量化研究终端 — RESEARCH_ONLY", f"状态：{brief.status}",
        f"分析截止：{brief.quant.analysis_cutoff.isoformat()}", f"引擎：V2.2_SHADOW / {brief.quant.engine_hash}",
        f"数据：{brief.quant.certification}；获利置信度：UNKNOWN", ""]
    labels = {"MARKET_OVERVIEW": "市场概览", "QUANT_EXPLORER": "量化因子", "PORTFOLIO_RISK": "组合风险",
        "RESEARCH_WORKSPACE": "研究与反证", "DECISION_CONSOLE": "决策条件", "EXPERIMENT_LABORATORY": "实验室", "OPERATIONAL_HEALTH": "运行健康"}
    for key, value in brief.views.items():
        lines.append(labels[key])
        if key == "QUANT_EXPLORER":
            for row in brief.quant.rows:
                lines.append(f"  {row.symbol}  score={row.score if row.score is not None else 'UNKNOWN'}  rank={row.rank if row.rank is not None else 'UNKNOWN'}  {row.chinese_explanation}")
        else:
            lines.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        lines.append("")
    lines.append("人工审核：这些结果没有订单、成交或执行授权。金融 Alpha 尚未证明。")
    return "\n".join(lines)


def terminal_model_context(snapshot: QuantTerminalSnapshot) -> dict[str, Any]:
    """Input to the existing native chain; hash-bound, numerical and prose separate."""
    rows = {r.symbol: r for r in snapshot.packet.symbols} if snapshot.packet else {}
    view = QuantModelView(analysis_cutoff=snapshot.analysis_cutoff, snapshot_hash=snapshot.digest,
        engine_hash=snapshot.engine_hash, policy_hash=snapshot.policy_hash, risk_policy_hash=snapshot.risk_policy_hash, input_hashes=snapshot.input_hashes,
        certification=snapshot.certification, regime=snapshot.packet.regime if snapshot.packet else None,
        rows=tuple(QuantModelRow(signal=r, quant=rows[r.symbol].score if r.symbol in rows else None,
            desired_weight=rows[r.symbol].preferred_exposure if r.symbol in rows else Decimal(0),
            feasible_weight=rows[r.symbol].feasible_exposure if r.symbol in rows else Decimal(0)) for r in snapshot.rows),
        unknowns=snapshot.packet.important_unknowns if snapshot.packet else snapshot.reasons)
    return {"quant_terminal_view": view.model_dump(mode="json"), "quant_terminal_view_hash": fingerprint(view)}


def validate_model_input_budget(context: dict[str, Any], budget: TerminalBudget) -> None:
    # UTF-8 bytes are a conservative upper bound, not an observed token count.
    if len(json.dumps(context, ensure_ascii=False).encode()) > budget.max_model_input_tokens:
        raise ValueError("TERMINAL_MODEL_INPUT_TOKEN_UPPER_BOUND_EXCEEDED")


def review_terminal(brief: TerminalBrief, request: DailyResearchInput, settings: ResearchSettings,
                    runtime: ResearchModelRuntime, *, budget: TerminalBudget | None = None) -> NativeResearchResult:
    """Explicit opt-in to the existing bounded chain; no persistent memory/cache.

    Caller config owns model/deadline. Deterministic brief survives any provider
    failure. This function never opens the canonical application or paper store.
    """
    from meridian.daily_research import DailyResearchInput
    from meridian.gpt_native_research import ExecutionState, GPTNativeResearchOrchestrator
    if request.analysis_cutoff != brief.quant.analysis_cutoff:
        raise ValueError("TERMINAL_SHARED_CUTOFF_REQUIRED")
    if brief.quant.status == "BLOCKED":
        raise ValueError("TERMINAL_MODEL_BLOCKED_UNQUALIFIED_QUANT")
    if brief.quant.status == "SYNTHETIC_DIAGNOSTIC" and request.mode == "LIVE":
        raise ValueError("TERMINAL_SYNTHETIC_NOT_LIVE")
    context = terminal_model_context(brief.quant)
    validate_model_input_budget(context, budget or TerminalBudget())
    prepared = DailyResearchInput.model_validate({**request.model_dump(), "market_context": context})
    return GPTNativeResearchOrchestrator(runtime=runtime).run(prepared, settings=settings,
        research_data_status="PASS", execution_data_status="BLOCKED_POLICY",
        execution_state=ExecutionState.BLOCKED_POLICY)


def research_quality_scorecard(result: NativeResearchResult) -> dict[str, Any]:
    """Observable explanation quality, not a financial performance score."""
    from meridian.gpt_native_research import InvocationStatus
    supported = sum(bool(c.supporting_evidence_ids) for c in result.claims)
    catalog = {e.evidence_id for e in result.evidence}
    cited = {e for c in result.claims for e in (*c.supporting_evidence_ids, *c.contradicting_evidence_ids)}
    shared: dict[str, int] = {}
    individual = 0
    usage: dict[str, int] = {}
    for stage in result.stages.values():
        key = stage.diagnostic.get("shared_invocation_id")
        if key:
            if str(key) in shared:
                continue
            shared[str(key)] = stage.duration_ms
        else:
            individual += stage.duration_ms
        for name, count in stage.usage.items():
            usage[name] = usage.get(name, 0) + count
    return {"version": "research-quality-scorecard.v1", "research_state": result.research_state.value,
        "source_count": len(result.evidence), "claim_count": len(result.claims), "cited_claim_count": supported,
        "evidence_coverage_fraction": len(cited & catalog) / len(catalog) if catalog else None,
        "contradiction_count": len(result.skeptic.contradicting_evidence) if result.skeptic else None,
        "skeptic_challenge_count": len(result.skeptic.challenges) if result.skeptic else None,
        "disagreement_score": result.disagreement_score,
        "successful_logical_stages": sum(s.status is InvocationStatus.SUCCESS for s in result.stages.values()),
        "model_wall_ms": individual + sum(shared.values()), "shared_calls": len(shared),
        "token_usage": usage or None, "cost": None, "review_time_saved": None,
        "probability_calibration": "UNCALIBRATED", "predictive_confidence": None,
        "financial_returns_improved": "NOT_EVALUATED",
        "numeric_correspondence_is_semantic_truth": False}
