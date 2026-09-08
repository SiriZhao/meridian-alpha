"""Retired Skill helper; use Meridian's canonical doctor command instead."""

from __future__ import annotations

import json


def main() -> int:
    print(json.dumps({
        "status": "SKILL_HELPER_RETIRED",
        "next_action": "Run scripts/run_meridian.ps1 doctor --json from the Meridian project root.",
        "reason": "This helper does not implement a parallel preflight or accept legacy profiles.",
    }))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
