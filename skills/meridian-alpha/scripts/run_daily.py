"""Retired Skill helper; the live Skill supplies the sole canonical workflow."""

from __future__ import annotations

import json


def main() -> int:
    print(json.dumps({
        "status": "SKILL_HELPER_RETIRED",
        "next_action": "Run scripts/run_meridian.ps1 paper run --account Schwab-Paper --json from the Meridian project root.",
        "reason": "This helper never creates snapshots, uses fixtures, or runs a parallel daily pipeline.",
    }))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
