"""Versioned Skill workflow contract; selection never dispatches external tools."""
from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.schemas import StableModel

READ_ONLY_RESEARCH_TOOLS = frozenset({"runtime_status", "market_snapshot", "account_snapshot", "company_facts",
    "event_evidence", "macro_context", "research_packet", "quant_metrics", "portfolio_context", "risk_analysis",
    "forward_evidence", "audit_lookup", "validate_market_evidence", "quant_research_snapshot",
    "portfolio_what_if", "research_evidence_trace", "decision_research_brief", "research_paper_plan"})


class WorkflowDefaults(StableModel):
    max_tool_calls: int = Field(ge=1, le=8)
    wall_seconds: int = Field(ge=1, le=180)
    nested_model_calls: Literal[0]
    missing_data: str = Field(min_length=1, max_length=500)
    risk_checks: tuple[str, ...] = Field(min_length=1, max_length=10)
    output_schema: Literal["meridian-decision-brief.v1"]
    prohibited_side_effects: tuple[str, ...] = Field(min_length=1, max_length=10)


class WorkflowRule(StableModel):
    intent: str = Field(pattern=r"^[A-Z_]{1,64}$")
    required_evidence: tuple[str, ...] = Field(min_length=1, max_length=10)
    tools: tuple[str, ...] = Field(min_length=1, max_length=8)
    gpt_reasoning: str = Field(min_length=1, max_length=1000)


class ToolFactReceipt(StableModel):
    tool: str = Field(min_length=1, max_length=80)
    analysis_cutoff: AwareDatetime
    observed_at: AwareDatetime
    available_at: AwareDatetime
    valid_until: AwareDatetime
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["AVAILABLE", "BLOCKED", "UNVERIFIED"]

    @model_validator(mode="after")
    def identity(self) -> ToolFactReceipt:
        if self.tool not in READ_ONLY_RESEARCH_TOOLS:
            raise ValueError("WORKFLOW_UNAUTHORIZED_FACT_TOOL")
        if not self.observed_at <= self.available_at <= self.analysis_cutoff <= self.valid_until:
            raise ValueError("WORKFLOW_FACT_TIMING_INVALID")
        return self


class SkillWorkflowContract(StableModel):
    version: Literal["meridian-skill-workflows.v2"]
    authority: Literal["ADVISORY_ONLY"]
    defaults: WorkflowDefaults
    workflows: tuple[WorkflowRule, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def bounded_allowlist(self) -> SkillWorkflowContract:
        if len({w.intent for w in self.workflows}) != len(self.workflows):
            raise ValueError("WORKFLOW_DUPLICATE_INTENT")
        for rule in self.workflows:
            if set(rule.tools) - READ_ONLY_RESEARCH_TOOLS or len(set(rule.tools)) != len(rule.tools):
                raise ValueError("WORKFLOW_TOOL_NOT_ALLOWLISTED_OR_DUPLICATE")
            if len(rule.tools) > self.defaults.max_tool_calls:
                raise ValueError("WORKFLOW_TOOL_BUDGET_EXCEEDED")
        return self

    def plan(self, intent: str, *, analysis_cutoff: AwareDatetime,
             receipts: tuple[ToolFactReceipt, ...] = (), expected_inputs: dict[str, str] | None = None) -> tuple[str, ...]:
        if len(receipts) > 8 or len({r.tool for r in receipts}) != len(receipts):
            raise ValueError("WORKFLOW_FACT_RECEIPT_LIMIT_OR_DUPLICATE")
        available_fact_tools = {r.tool for r in receipts if r.status == "AVAILABLE" and r.analysis_cutoff == analysis_cutoff
            and r.valid_until >= analysis_cutoff and r.input_hash == (expected_inputs or {}).get(r.tool)}
        row = next((w for w in self.workflows if w.intent == intent), None)
        if row is None:
            raise ValueError("WORKFLOW_UNKNOWN_INTENT")
        return tuple(t for t in row.tools if t not in available_fact_tools)
