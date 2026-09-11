"""Astra-facing, evidence-first research contracts.

These models define what Astra may synthesize. They deliberately carry no
execution authority and validate that observed facts resolve to Meridian-owned
evidence known by the declared cutoff.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.evidence_graph import EvidenceGraph
from meridian.runtime import RuntimePaths
from meridian.schemas import StableModel


class ResearchIntent(StrEnum):
    COMPANY_RESEARCH = "COMPANY_RESEARCH"
    PORTFOLIO_REVIEW = "PORTFOLIO_REVIEW"
    EARNINGS_REVIEW = "EARNINGS_REVIEW"
    NEWS_IMPACT = "NEWS_IMPACT"
    BUY_REVIEW = "BUY_REVIEW"
    SELL_REVIEW = "SELL_REVIEW"
    PRE_MORTEM = "PRE_MORTEM"
    DIP_RESEARCH = "DIP_RESEARCH"
    DAILY_RESEARCH = "DAILY_RESEARCH"


class ClaimKind(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    FORECAST = "FORECAST"
    UNKNOWN = "UNKNOWN"


class ResearchEvidence(StableModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=512)
    observed_at: AwareDatetime
    known_at: AwareDatetime
    analysis_cutoff: AwareDatetime
    freshness: str = Field(min_length=1, max_length=64)
    data_quality: str = Field(min_length=1, max_length=64)
    provenance: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def time_bound(self) -> ResearchEvidence:
        if self.observed_at > self.analysis_cutoff or self.known_at > self.analysis_cutoff:
            raise ValueError("RESEARCH_EVIDENCE_AFTER_CUTOFF")
        return self


class ResearchClaim(StableModel):
    kind: ClaimKind
    statement: str = Field(min_length=1, max_length=4000)
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def factual_claim_requires_evidence(self) -> ResearchClaim:
        if self.kind is ClaimKind.FACT and not self.evidence_ids:
            raise ValueError("FACT_REQUIRES_EVIDENCE")
        if self.kind is ClaimKind.UNKNOWN and self.evidence_ids:
            raise ValueError("UNKNOWN_MUST_NOT_ASSERT_EVIDENCE")
        return self


class AuditMetadata(StableModel):
    provider: str = "CODEX_CLI"
    model: str = "gpt-6-astra"
    skill_version: str = "meridian-astra-v1"
    audit_reference: str | None = None
    execution_authority: Literal["NONE"] = "NONE"


class MeridianResearchResult(StableModel):
    """Canonical non-executable research output for Astra/Skill workflows."""

    subject: str = Field(min_length=1, max_length=128)
    analysis_cutoff: AwareDatetime
    research_question: str = Field(min_length=1, max_length=4000)
    intent: ResearchIntent
    facts: tuple[ResearchClaim, ...] = ()
    inferences: tuple[ResearchClaim, ...] = ()
    forecasts: tuple[ResearchClaim, ...] = ()
    evidence: tuple[ResearchEvidence, ...] = ()
    contradicting_evidence: tuple[ResearchEvidence, ...] = ()
    unknowns: tuple[str, ...] = ()
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    valuation_context: str | None = None
    portfolio_context: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    data_quality: str = "UNKNOWN"
    evidence_coverage: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    recommendation: str = "NO_ACTION"
    evidence_graph: EvidenceGraph | None = None
    audit_metadata: AuditMetadata = AuditMetadata()

    @model_validator(mode="after")
    def cited_evidence_is_known(self) -> MeridianResearchResult:
        items = (*self.evidence, *self.contradicting_evidence)
        identifiers = {item.evidence_id for item in items}
        if len(identifiers) != len(items):
            raise ValueError("RESEARCH_DUPLICATE_EVIDENCE_ID")
        if any(item.known_at > self.analysis_cutoff or item.observed_at > self.analysis_cutoff for item in items):
            raise ValueError("RESEARCH_RESULT_EVIDENCE_AFTER_CUTOFF")
        for claims, kind in ((self.facts, ClaimKind.FACT), (self.inferences, ClaimKind.INFERENCE), (self.forecasts, ClaimKind.FORECAST)):
            if any(claim.kind is not kind for claim in claims):
                raise ValueError("RESEARCH_CLAIM_SECTION_MISMATCH")
        if not items and (self.confidence or self.evidence_coverage):
            raise ValueError("RESEARCH_CONFIDENCE_REQUIRES_EVIDENCE")
        for claim in (*self.facts, *self.inferences, *self.forecasts):
            if not set(claim.evidence_ids) <= identifiers:
                raise ValueError("RESEARCH_CITATION_UNKNOWN")
        if self.evidence_graph is not None:
            graph_evidence_ids = {
                node.evidence_id for node in self.evidence_graph.nodes if node.evidence_id
            }
            if not graph_evidence_ids <= identifiers:
                raise ValueError("RESEARCH_GRAPH_EVIDENCE_UNKNOWN")
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode("utf-8")).hexdigest()


def persist_research_result(
    result: MeridianResearchResult, paths: RuntimePaths
) -> Path:
    """Persist one immutable, sanitized research result under RuntimePaths."""
    directory = paths.audit / "research-results"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{result.content_hash}.json"
    content = result.stable_json() + "\n"
    if destination.exists():
        if destination.read_text(encoding="utf-8") != content:
            raise ValueError("RESEARCH_AUDIT_IMMUTABILITY_CONFLICT")
        return destination
    try:
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        if destination.read_text(encoding="utf-8") != content:
            raise ValueError("RESEARCH_AUDIT_IMMUTABILITY_CONFLICT") from error
    return destination


def evidence_envelope(*, source: str, observed_at: datetime, known_at: datetime,
                      analysis_cutoff: datetime, freshness: str, data_quality: str,
                      provenance: str, evidence_id: str) -> ResearchEvidence:
    """Small deterministic constructor used by tool adapters and tests."""
    return ResearchEvidence(
        evidence_id=evidence_id,
        source=source,
        observed_at=observed_at,
        known_at=known_at,
        analysis_cutoff=analysis_cutoff,
        freshness=freshness,
        data_quality=data_quality,
        provenance=provenance,
    )



