"""External acceptance helper: invoke exactly one real GPT research role."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

from meridian.config import load_policies
from meridian.gpt_native_research import (
    CodexResearchModelRuntime,
    DecisionSynthesisOutput,
    PrimaryAnalystOutput,
    ScenarioOutput,
    SkepticOutput,
)
from meridian.runtime import policy_directory
from meridian.shadow_evaluation import ShadowResearchRunner


def main() -> int:
    role = sys.argv[1] if len(sys.argv) == 2 else ""
    schema_types = {
        "PRIMARY_ANALYST": PrimaryAnalystOutput,
        "SKEPTIC": SkepticOutput,
        "SCENARIO_ANALYST": ScenarioOutput,
        "DECISION_SYNTHESIZER": DecisionSynthesisOutput,
    }
    if role not in schema_types:
        print(json.dumps({"status": "INVALID_ROLE", "role": role}))
        return 2
    settings = load_policies(policy_directory()).models.research
    if settings is None:
        print(json.dumps({"status": "NOT_AVAILABLE", "error_type": "RESEARCH_NOT_CONFIGURED"}))
        return 3
    route = ShadowResearchRunner.route(settings)[role]
    evidence_id = "external-fixture-aapl-price"
    base = {
        "research_question": "Assess only the supplied frozen evidence.",
        "analysis_cutoff": datetime.now(UTC).isoformat(),
        "evidence": [{
            "evidence_id": evidence_id,
            "symbol": "AAPL",
            "category": "PRICE",
            "source_type": "STRUCTURED_MARKET",
            "structured_value": {"last": "100"},
            "verification_status": "VERIFIED",
        }],
        "prior_thesis": None,
        "data_limitations": ["Single frozen evidence item; no execution authority."],
    }
    if role == "SKEPTIC":
        input_data = {**base, "primary": None, "instruction": "Challenge unsupported assumptions only."}
    elif role == "SCENARIO_ANALYST":
        input_data = {**base, "primary": None, "skeptic": None}
    elif role == "DECISION_SYNTHESIZER":
        input_data = {**base, "primary": None, "skeptic": None, "scenarios": None, "risk_constraints": {"execution_authority": "NONE"}}
    else:
        input_data = base
    result = CodexResearchModelRuntime().invoke(
        role,
        input_data,
        schema_types[role].model_json_schema(),
        int(route["timeout_seconds"]),
        model=str(route["model"]),
        reasoning_effort=str(route["reasoning_effort"]),
    )
    schema_valid = False
    evidence_ids_valid = False
    if result.status.value == "SUCCESS" and result.output is not None:
        try:
            parsed = schema_types[role].model_validate(result.output)
            referenced: set[str] = set()
            if isinstance(parsed, PrimaryAnalystOutput):
                referenced.update(parsed.evidence_used)
                for claim in parsed.supporting_claims:
                    referenced.update(claim.supporting_evidence_ids)
                    referenced.update(claim.contradicting_evidence_ids)
            elif isinstance(parsed, SkepticOutput):
                referenced.update(parsed.contradicting_evidence)
            elif isinstance(parsed, DecisionSynthesisOutput):
                referenced.update(parsed.key_support)
            schema_valid = True
            evidence_ids_valid = referenced <= {evidence_id}
        except ValueError:
            schema_valid = False
    payload: dict[str, Any] = {
        "status": result.status.value,
        "role": role,
        "model": result.model,
        "reasoning_effort": result.reasoning_effort,
        "duration_ms": result.duration_ms,
        "schema_valid": schema_valid,
        "evidence_ids_valid": evidence_ids_valid,
        "attempt_count": result.attempt_count,
        "repair_attempted": False,
        "repair_success": False,
        "failure_category": result.error_type,
        "diagnostic": result.diagnostic,
        "usage": result.usage if result.usage else "USAGE_UNAVAILABLE",
    }
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0 if result.status.value == "SUCCESS" and schema_valid and evidence_ids_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())