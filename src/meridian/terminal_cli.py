"""Local read-only terminal: explicit input file, stdout only, no runtime service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from meridian.research_terminal import QuantTerminalRequest
from meridian.terminal_service import TerminalPlanner, render_terminal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian terminal")
    parser.add_argument("input", type=Path, help="Explicit QuantTerminalRequest JSON; never a canonical account file")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--engine", choices=("V2.2_SHADOW", "V2.3_SHADOW"), default=None,
        help="Research engine override; existing files retain their explicit engine")
    parser.add_argument("--research-input", type=Path, help="Explicit source/time-bound DailyResearchInput; no account inference")
    parser.add_argument("--gpt", action="store_true", help="Opt in to the bounded native four-role chain; requires research input")
    parser.add_argument("--paper-review", type=Path, help="Explicit sanctioned PaperReviewRequest; pure planning without ledger/fills")
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 2000000:
            raise ValueError("TERMINAL_FILE_LIMIT_2MB")
        request = QuantTerminalRequest.model_validate_json(args.input.read_text(encoding="utf-8"))
        request = request.model_copy(update={"engine": args.engine or request.engine})
        brief = TerminalPlanner().build(request)
        ticket = None
        if args.paper_review:
            from meridian.research_order_review import PaperReviewRequest, review_paper_request
            from meridian.research_terminal import PortfolioWhatIfRequest, fingerprint
            if args.paper_review.stat().st_size > 2000000:
                raise ValueError('TERMINAL_PAPER_REVIEW_FILE_LIMIT_2MB')
            review = PaperReviewRequest.model_validate_json(args.paper_review.read_text(encoding='utf-8'))
            if fingerprint(review.quant) != fingerprint(request):
                raise ValueError('TERMINAL_PAPER_REVIEW_INPUT_MISMATCH')
            ticket = review_paper_request(review)
            if review.account:
                brief = TerminalPlanner().build(request, portfolio=PortfolioWhatIfRequest(
                    analysis_cutoff=request.analysis_cutoff, account=review.account, desired=(), metadata=request.metadata))
        if args.research_input:
            from meridian.config import load_policies
            from meridian.daily_research import DailyResearchInput
            from meridian.decision_brief import generate_decision_brief, render_decision_brief
            from meridian.gpt_native_research import CodexResearchModelRuntime
            from meridian.runtime import policy_directory
            from meridian.terminal_service import review_terminal
            if args.research_input.stat().st_size > 2000000:
                raise ValueError("TERMINAL_RESEARCH_FILE_LIMIT_2MB")
            research = DailyResearchInput.model_validate_json(args.research_input.read_text(encoding="utf-8"))
            settings = load_policies(policy_directory()).models.research
            if args.gpt and settings is None:
                raise ValueError('TERMINAL_GPT_SETTINGS_REQUIRED')
            model = review_terminal(brief, research, settings, CodexResearchModelRuntime()) if args.gpt and settings else None
            decision = generate_decision_brief(brief, request=research, model_result=model, paper_review=ticket)
            print(decision.model_dump_json(indent=2) if args.json else render_decision_brief(decision))
            return 1 if brief.status == "BLOCKED" else 0
        if args.gpt:
            raise ValueError("TERMINAL_GPT_REQUIRES_EXPLICIT_RESEARCH_INPUT")
        if ticket:
            from meridian.decision_brief import generate_decision_brief, render_decision_brief
            decision = generate_decision_brief(brief, paper_review=ticket)
            print(decision.model_dump_json(indent=2) if args.json else render_decision_brief(decision))
            return 1 if ticket.state == 'BLOCKED' else 0
        print(brief.model_dump_json(indent=2) if args.json else render_terminal(brief))
        return 1 if brief.status == "BLOCKED" else 0
    except (OSError, ValueError):
        # Input and exception text may contain secrets; never echo them.
        print(json.dumps({"status": "BLOCKED", "reason": "TERMINAL_INPUT_OR_BUDGET_REJECTED", "broker_submission": "DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
