"""Check typed terminal schemas and the shipped allowlisted Skill contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from meridian.decision_brief import DecisionBrief
from meridian.numerical_grounding import NumericalCitation
from meridian.research_order_review import ManualOrderTicket, PaperReviewRequest
from meridian.research_recommendations import ResearchPricePlan, ResearchRecommendation
from meridian.research_terminal import (
    EvidenceTraceRequest,
    EvidenceTraceResult,
    PortfolioWhatIfRequest,
    PortfolioWhatIfResult,
    QuantTerminalRequest,
    QuantTerminalSnapshot,
)
from meridian.research_workflows import SkillWorkflowContract
from meridian.terminal_service import TerminalBrief, TerminalBudget

ROOT = Path(__file__).resolve().parents[1]
MODELS = (QuantTerminalRequest, QuantTerminalSnapshot, PortfolioWhatIfRequest,
    PortfolioWhatIfResult, EvidenceTraceRequest, EvidenceTraceResult,
    TerminalBrief, TerminalBudget, DecisionBrief, ResearchRecommendation, ResearchPricePlan,
    ManualOrderTicket, PaperReviewRequest, NumericalCitation, SkillWorkflowContract)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Generate source schemas only; never a runtime artifact")
    args = parser.parse_args()
    schema_path = ROOT / "schemas/research-terminal.v1.schema.json"
    # Each named contract is a standalone schema: its $defs remain local.
    contracts = {model.__name__: model.model_json_schema() for model in MODELS}
    if args.write:
        schema_path.write_text(json.dumps(contracts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if json.loads(schema_path.read_text(encoding="utf-8")) != contracts:
        raise ValueError("TERMINAL_TYPED_SCHEMA_DRIFT")
    SkillWorkflowContract.model_validate_json((ROOT / "skills/meridian-alpha/references/terminal-workflows.json").read_text(encoding="utf-8"))
    print("TERMINAL_CONTRACTS_AND_WORKFLOWS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
