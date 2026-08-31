"""Capability-only preflight for the portable Meridian Alpha Skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any

SENSITIVE_KEY = re.compile(
    r"(?i)(account[_-]?(?:number|id)|access[_-]?token|refresh[_-]?token|authorization|password|secret|credential|connector[_-]?payload|raw[_-]?response)"
)
TRUTHY = {"1", "true", "yes", "on"}
PROFILES = {"TEST", "REPLAY", "SHADOW_LIVE", "MANUAL_DECISION_SUPPORT"}


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUTHY


def _sensitive(value: Any) -> bool:
    if isinstance(value, dict):
        return any(SENSITIVE_KEY.search(str(key)) or _sensitive(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_sensitive(item) for item in value)
    return False


def account_input_status(path: Path | None) -> str:
    if path is None:
        return "MISSING"
    if not path.is_file():
        return "MISSING"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "INVALID"
    if not isinstance(payload, dict) or _sensitive(payload):
        return "REJECTED_SENSITIVE"
    required = {"snapshot_id", "as_of", "currency", "cash", "holdings"}
    return "VALID" if required.issubset(payload) else "INCOMPLETE"


def evaluate(profile: str, snapshot: Path | None = None) -> dict[str, str]:
    runtime = "AVAILABLE" if importlib.util.find_spec("meridian") is not None else "UNAVAILABLE"
    account = account_input_status(snapshot)
    network = "AVAILABLE" if _enabled("MERIDIAN_NETWORK_AVAILABLE") else "UNAVAILABLE"
    sec = "AVAILABLE" if _enabled("MERIDIAN_SEC_CERTIFIED") else ("REPLAY_ONLY" if profile == "REPLAY" else "UNAVAILABLE")
    deepseek = "AVAILABLE" if _enabled("MERIDIAN_LIVE_DEEPSEEK_AVAILABLE") else ("REPLAY_ONLY" if profile == "REPLAY" else "UNAVAILABLE")
    quote = "CERTIFIED" if _enabled("MERIDIAN_CERTIFIED_QUOTE_AVAILABLE") else "UNAVAILABLE"
    profile_allowed = profile in {"TEST", "REPLAY"}
    if profile == "SHADOW_LIVE":
        profile_allowed = runtime == "AVAILABLE" and network == "AVAILABLE"
    if profile == "MANUAL_DECISION_SUPPORT":
        profile_allowed = (
            runtime == "AVAILABLE"
            and account == "VALID"
            and sec == "AVAILABLE"
            and quote == "CERTIFIED"
        )
    if profile not in PROFILES:
        profile_allowed = False
    if runtime != "AVAILABLE":
        overall = "MERIDIAN_RUNTIME_UNAVAILABLE"
    elif not profile_allowed:
        overall = "BLOCKED_PROFILE_CAPABILITY"
    else:
        overall = "READY"
    return {
        "RUNTIME": runtime,
        "ACCOUNT_INPUT": account,
        "NETWORK": network,
        "SEC": sec,
        "DEEPSEEK": deepseek,
        "QUOTE": quote,
        "PROFILE_ALLOWED": "YES" if profile_allowed else "NO",
        "OVERALL": overall,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Meridian portable capability preflight")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="TEST")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    for key, value in evaluate(args.profile, args.snapshot).items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())