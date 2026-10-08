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
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 2000000:
            raise ValueError("TERMINAL_FILE_LIMIT_2MB")
        request = QuantTerminalRequest.model_validate_json(args.input.read_text(encoding="utf-8"))
        brief = TerminalPlanner().build(request)
        print(brief.model_dump_json(indent=2) if args.json else render_terminal(brief))
        return 1 if brief.status == "BLOCKED" else 0
    except (OSError, ValueError):
        # Input and exception text may contain secrets; never echo them.
        print(json.dumps({"status": "BLOCKED", "reason": "TERMINAL_INPUT_OR_BUDGET_REJECTED", "broker_submission": "DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
