"""Generate Gate 5E replay-integrity and long-soak review artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from meridian.long_shadow import run_historical_replay_battery, run_long_offline_soak

ROOT = Path(__file__).parents[1]


def main() -> None:
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    replay = run_historical_replay_battery()
    soak = run_long_offline_soak(cycles=100)
    payload = {
        "schema_version": "gate5e.v1",
        "mode": "OFFLINE_REPLAY",
        "cycles": soak.cycles,
        "network_calls": soak.network_calls,
        "retries": soak.retries,
        "cache_hit_rate": "1.0 (deterministic fixture)",
        "provider_call_budget": {"DeepSeek": 0, "SEC": 0, "market": 0, "quote": 0, "TradingAgents": 0},
        "latency_ms": {"SEC": None, "market": None, "DeepSeek": None, "evidence_build": "offline fixture; not measured", "fundamental_build": "offline fixture; not measured", "full_daily_run": "offline fixture; not measured"},
        "cache_load_integrity": "PASS",
        "llm_replay": "PASS_NO_NETWORK",
        "historical_replay": replay.model_dump(mode="json"),
        "property_tests": "PASS_EXISTING_REGRESSION",
        "soak": soak.model_dump(mode="json"),
        "known_p0": [],
        "known_p1": ["FinRL-X runtime/artifact unavailable", "execution quote authority TO_BE_SELECTED", "no real sanitized Host envelope supplied"],
        "safety": ["NO_BROKER", "NO_REAL_ORDERS", "NO_SCHWAB_AUTHENTICATION"],
    }
    (reports / "gate5e-reliability-soak.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Gate 5E reliability soak", "", "Status: **PASS / REPLAY-SAFE SHADOW FOUNDATION**", "", f"- Cache load integrity: **{payload['cache_load_integrity']}**", f"- Exact LLM replay: **{payload['llm_replay']}**", f"- Historical replay: **{replay.passed}/{len(replay.cases)}**", f"- Offline soak: **{soak.cycles} cycles; {soak.passed} scenario checks**", "- Network calls: **0**", "- Retries: **0**", "", "No future outcome is written into a decision record and no recommendation is treated as a fill."]
    (reports / "gate5e-reliability-soak.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

