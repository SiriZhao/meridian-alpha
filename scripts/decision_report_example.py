"""Reproduce a fixture-only Chinese decision report, never today's market."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.decision_brief import generate_decision_brief, render_decision_brief  # noqa: E402
from meridian.terminal_service import TerminalPlanner  # noqa: E402
from tests.test_research_decisions import quant_request, research_input  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-source-fixture', action='store_true')
    args = parser.parse_args()
    request = quant_request()
    evidence = research_input(request)
    decision = generate_decision_brief(TerminalPlanner().build(request), request=evidence)
    if args.write_source_fixture:
        output = Path(__file__).resolve().parents[1] / 'docs/decision-integration'
        output.mkdir(exist_ok=True)
        (output/'golden-decision.json').write_text(json.dumps(decision.model_dump(mode='json'), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output/'sample-fixture-report.md').write_text('FIXTURE_ONLY / SYNTHETIC_DIAGNOSTIC — NOT TODAY\n\n' + render_decision_brief(decision), encoding='utf-8')
    else:
        print('FIXTURE_ONLY / SYNTHETIC_DIAGNOSTIC — NOT TODAY\n\n' + render_decision_brief(decision))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
