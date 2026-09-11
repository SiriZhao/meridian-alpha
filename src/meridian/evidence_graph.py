"""Project-owned, validated evidence graph for Astra research synthesis."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from meridian.schemas import StableModel


class EvidenceNodeType(StrEnum):
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"
    CONTRADICTION = "CONTRADICTION"
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"


class EvidenceRelationType(StrEnum):
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    INVALIDATED_BY = "INVALIDATED_BY"
    DERIVED_FROM = "DERIVED_FROM"


class EvidenceGraphNode(StableModel):
    node_id: str = Field(min_length=1, max_length=128)
    node_type: EvidenceNodeType
    statement: str = Field(min_length=1, max_length=4000)
    evidence_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def evidence_identity_is_explicit(self) -> EvidenceGraphNode:
        if self.node_type is EvidenceNodeType.EVIDENCE and not self.evidence_id:
            raise ValueError("EVIDENCE_NODE_REQUIRES_EVIDENCE_ID")
        if self.node_type is not EvidenceNodeType.EVIDENCE and self.evidence_id:
            raise ValueError("NON_EVIDENCE_NODE_MUST_NOT_DECLARE_EVIDENCE_ID")
        return self


class EvidenceGraphRelation(StableModel):
    from_node_id: str = Field(min_length=1, max_length=128)
    to_node_id: str = Field(min_length=1, max_length=128)
    relation: EvidenceRelationType


class EvidenceGraphClaim(StableModel):
    claim_id: str = Field(min_length=1, max_length=128)
    claim_type: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    unknown_ids: tuple[str, ...] = ()
    contradiction_resolution: str | None = None


class EvidenceGraph(StableModel):
    nodes: tuple[EvidenceGraphNode, ...] = ()
    relationships: tuple[EvidenceGraphRelation, ...] = ()
    claims: tuple[EvidenceGraphClaim, ...] = ()

    @model_validator(mode="after")
    def references_resolve(self) -> EvidenceGraph:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("EVIDENCE_GRAPH_DUPLICATE_NODE_ID")
        if any(item.from_node_id not in node_ids or item.to_node_id not in node_ids for item in self.relationships):
            raise ValueError("EVIDENCE_GRAPH_DANGLING_NODE_REFERENCE")
        evidence_ids = {node.evidence_id for node in self.nodes if node.evidence_id}
        assumptions = {node.node_id for node in self.nodes if node.node_type is EvidenceNodeType.ASSUMPTION}
        unknowns = {node.node_id for node in self.nodes if node.node_type is EvidenceNodeType.UNKNOWN}
        claim_ids = {claim.claim_id for claim in self.claims}
        if len(claim_ids) != len(self.claims):
            raise ValueError("EVIDENCE_GRAPH_DUPLICATE_CLAIM_ID")
        for claim in self.claims:
            if not set((*claim.supporting_evidence_ids, *claim.contradicting_evidence_ids)) <= evidence_ids:
                raise ValueError("EVIDENCE_GRAPH_DANGLING_EVIDENCE_ID")
            if not set(claim.assumption_ids) <= assumptions:
                raise ValueError("EVIDENCE_GRAPH_DANGLING_ASSUMPTION_ID")
            if not set(claim.unknown_ids) <= unknowns:
                raise ValueError("EVIDENCE_GRAPH_DANGLING_UNKNOWN_ID")
            if (claim.claim_type == "FACT" or claim.confidence > 0) and not claim.supporting_evidence_ids:
                raise ValueError("EVIDENCE_GRAPH_UNSUPPORTED_CLAIM")
            if claim.contradicting_evidence_ids and not (claim.contradiction_resolution or claim.unknown_ids):
                raise ValueError("EVIDENCE_GRAPH_CONTRADICTION_UNRESOLVED")
        nodes = {node.node_id: node for node in self.nodes}
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        seen_edges: set[tuple[str, str, EvidenceRelationType]] = set()
        for edge in self.relationships:
            key = (edge.from_node_id, edge.to_node_id, edge.relation)
            if key in seen_edges:
                raise ValueError("EVIDENCE_GRAPH_DUPLICATE_RELATION")
            seen_edges.add(key)
            if edge.relation in {EvidenceRelationType.SUPPORTED_BY, EvidenceRelationType.CONTRADICTED_BY} and nodes[edge.to_node_id].node_type is not EvidenceNodeType.EVIDENCE:
                raise ValueError("EVIDENCE_GRAPH_RELATION_TYPE_MISMATCH")
            adjacency[edge.from_node_id].append(edge.to_node_id)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("EVIDENCE_GRAPH_CYCLE")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in adjacency[node_id]:
                visit(target)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in nodes:
            visit(node_id)
        return self
